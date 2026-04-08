"""
LeadScore AI - SaaS Lead Qualification Service
Flask + Stripe + Claude Haiku
"""

import os, json, time, hashlib, secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template_string
import stripe
import anthropic

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))

# --- Config ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "admin-secret-change-me")

PLANS = {
    "starter": {"price_id": os.environ.get("STRIPE_STARTER_PRICE", "price_starter"), "limit": 500, "clinics": 1},
    "pro":     {"price_id": os.environ.get("STRIPE_PRO_PRICE", "price_pro"),         "limit": 2000, "clinics": 3},
    "agency":  {"price_id": os.environ.get("STRIPE_AGENCY_PRICE", "price_agency"),    "limit": 10000, "clinics": 999},
}

# --- In-Memory Store (swap for Postgres/Redis in production) ---
tenants = {}   # api_key -> {name, email, plan, leads:[], usage_this_month, month, stripe_customer_id, created}
rate_limits = {}  # api_key -> [timestamps]

RATE_LIMIT_PER_MINUTE = 30


# --- Helpers ---
def generate_api_key():
    return "ls_" + secrets.token_hex(20)


def get_tenant(api_key):
    return tenants.get(api_key)


def check_rate_limit(api_key):
    now = time.time()
    window = rate_limits.setdefault(api_key, [])
    rate_limits[api_key] = [t for t in window if now - t < 60]
    if len(rate_limits[api_key]) >= RATE_LIMIT_PER_MINUTE:
        return False
    rate_limits[api_key].append(now)
    return True


def reset_monthly_usage(tenant):
    current_month = datetime.utcnow().strftime("%Y-%m")
    if tenant.get("month") != current_month:
        tenant["usage_this_month"] = 0
        tenant["month"] = current_month


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        tenant = get_tenant(key)
        if not tenant:
            return jsonify({"error": "Invalid API key"}), 401
        if not check_rate_limit(key):
            return jsonify({"error": "Rate limit exceeded (30/min)"}), 429
        request.tenant = tenant
        request.api_key = key
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key")
        if key != ADMIN_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def score_lead_with_ai(lead_data, custom_criteria=None):
    """Score a lead using Claude Haiku."""
    criteria_text = custom_criteria or "High-value service interest, has insurance or willing to self-pay, urgency signals, complete contact info, engagement signals in notes."

    prompt = f"""You are a lead scoring AI for a medical/dental clinic. Score this lead from 0-100.

Scoring criteria: {criteria_text}

Lead data:
{json.dumps(lead_data, indent=2)}

Respond in this exact JSON format only:
{{"score": <0-100>, "priority": "<HOT|WARM|COLD>", "reasoning": "<1-2 sentences>", "action": "<recommended next step>"}}"""

    if not ANTHROPIC_API_KEY:
        # Fallback scoring when no API key
        score = 50
        name = lead_data.get("name", "")
        email = lead_data.get("email", "")
        phone = lead_data.get("phone", "")
        notes = lead_data.get("notes", "")
        service = lead_data.get("service", "").lower()
        insurance = lead_data.get("insurance", "").lower()

        if email: score += 5
        if phone: score += 10
        if "implant" in service or "ortho" in service: score += 15
        if "ppo" in insurance or "self-pay" in insurance or "cash" in insurance: score += 10
        if len(notes) > 20: score += 5
        if any(w in notes.lower() for w in ["soon", "urgent", "asap", "week"]): score += 10
        score = min(score, 98)

        priority = "HOT" if score >= 80 else "WARM" if score >= 60 else "COLD"
        return {
            "score": score,
            "priority": priority,
            "reasoning": f"Fallback scoring (no AI key configured). Score based on completeness and service value.",
            "action": "Call within 1 hour." if priority == "HOT" else "Follow up within 4 hours." if priority == "WARM" else "Add to email nurture sequence."
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-20250414",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    # Parse JSON from response
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        if "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
            return json.loads(text)
        raise


# --- Routes ---

@app.route("/")
def index():
    return jsonify({
        "service": "LeadScore AI",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    })


@app.route("/docs")
def docs():
    return render_template_string(DOCS_HTML)


# --- Tenant Management (Admin) ---

@app.route("/admin/tenants", methods=["POST"])
@require_admin
def create_tenant():
    """Create a new tenant. Called after Stripe checkout or manually."""
    data = request.json
    api_key = generate_api_key()
    tenants[api_key] = {
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "plan": data.get("plan", "starter"),
        "custom_criteria": data.get("custom_criteria"),
        "leads": [],
        "usage_this_month": 0,
        "month": datetime.utcnow().strftime("%Y-%m"),
        "stripe_customer_id": data.get("stripe_customer_id"),
        "created": datetime.utcnow().isoformat()
    }
    return jsonify({"api_key": api_key, "plan": tenants[api_key]["plan"]}), 201


@app.route("/admin/tenants", methods=["GET"])
@require_admin
def list_tenants():
    summary = []
    for key, t in tenants.items():
        summary.append({
            "api_key": key[:12] + "...",
            "name": t["name"],
            "email": t["email"],
            "plan": t["plan"],
            "usage": t["usage_this_month"],
            "leads_total": len(t["leads"]),
            "created": t["created"]
        })
    return jsonify(summary)


# --- Lead Scoring ---

@app.route("/api/score", methods=["POST"])
@require_api_key
def score_lead():
    """Score a single lead. Main endpoint."""
    tenant = request.tenant
    reset_monthly_usage(tenant)

    plan_limit = PLANS.get(tenant["plan"], PLANS["starter"])["limit"]
    if tenant["usage_this_month"] >= plan_limit:
        return jsonify({"error": f"Monthly limit reached ({plan_limit}). Upgrade your plan."}), 402

    lead_data = request.json
    if not lead_data:
        return jsonify({"error": "No lead data provided"}), 400

    try:
        result = score_lead_with_ai(lead_data, tenant.get("custom_criteria"))
    except Exception as e:
        return jsonify({"error": f"Scoring failed: {str(e)}"}), 500

    # Store lead
    lead_record = {
        "id": secrets.token_hex(8),
        "data": lead_data,
        "score": result["score"],
        "priority": result["priority"],
        "reasoning": result["reasoning"],
        "action": result["action"],
        "scored_at": datetime.utcnow().isoformat(),
        "source": request.headers.get("X-Lead-Source", "api")
    }
    tenant["leads"].append(lead_record)
    tenant["usage_this_month"] += 1

    return jsonify(lead_record), 200


# --- Webhook Endpoint (for form integrations) ---

@app.route("/webhook/<api_key>", methods=["POST"])
def webhook_score(api_key):
    """Public webhook for form integrations. No header auth needed -- key is in URL."""
    tenant = get_tenant(api_key)
    if not tenant:
        return jsonify({"error": "Invalid API key"}), 401
    if not check_rate_limit(api_key):
        return jsonify({"error": "Rate limited"}), 429

    reset_monthly_usage(tenant)
    plan_limit = PLANS.get(tenant["plan"], PLANS["starter"])["limit"]
    if tenant["usage_this_month"] >= plan_limit:
        return jsonify({"error": "Monthly limit reached"}), 402

    # Accept both JSON and form-encoded
    if request.is_json:
        lead_data = request.json
    else:
        lead_data = dict(request.form)

    try:
        result = score_lead_with_ai(lead_data, tenant.get("custom_criteria"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    lead_record = {
        "id": secrets.token_hex(8),
        "data": lead_data,
        "score": result["score"],
        "priority": result["priority"],
        "reasoning": result["reasoning"],
        "action": result["action"],
        "scored_at": datetime.utcnow().isoformat(),
        "source": request.headers.get("X-Lead-Source", "webhook")
    }
    tenant["leads"].append(lead_record)
    tenant["usage_this_month"] += 1

    return jsonify(lead_record), 200


# --- Dashboard ---

@app.route("/api/leads", methods=["GET"])
@require_api_key
def get_leads():
    """Get scored leads for this tenant."""
    tenant = request.tenant
    leads = tenant["leads"]

    # Filters
    priority = request.args.get("priority")
    if priority:
        leads = [l for l in leads if l["priority"] == priority.upper()]

    min_score = request.args.get("min_score", type=int)
    if min_score:
        leads = [l for l in leads if l["score"] >= min_score]

    # Sort by score desc (default)
    sort = request.args.get("sort", "score_desc")
    if sort == "score_desc":
        leads = sorted(leads, key=lambda x: x["score"], reverse=True)
    elif sort == "newest":
        leads = sorted(leads, key=lambda x: x["scored_at"], reverse=True)

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    start = (page - 1) * per_page

    return jsonify({
        "leads": leads[start:start + per_page],
        "total": len(leads),
        "page": page,
        "per_page": per_page
    })


@app.route("/api/usage", methods=["GET"])
@require_api_key
def get_usage():
    """Usage stats for this tenant."""
    tenant = request.tenant
    reset_monthly_usage(tenant)
    plan = PLANS.get(tenant["plan"], PLANS["starter"])

    leads = tenant["leads"]
    hot = sum(1 for l in leads if l["priority"] == "HOT")
    warm = sum(1 for l in leads if l["priority"] == "WARM")
    cold = sum(1 for l in leads if l["priority"] == "COLD")
    avg_score = sum(l["score"] for l in leads) / len(leads) if leads else 0

    return jsonify({
        "plan": tenant["plan"],
        "usage_this_month": tenant["usage_this_month"],
        "monthly_limit": plan["limit"],
        "remaining": plan["limit"] - tenant["usage_this_month"],
        "total_leads_scored": len(leads),
        "breakdown": {"hot": hot, "warm": warm, "cold": cold},
        "average_score": round(avg_score, 1)
    })


# --- Stripe Integration ---

@app.route("/api/checkout", methods=["POST"])
def create_checkout():
    """Create a Stripe checkout session for a plan."""
    data = request.json
    plan_name = data.get("plan", "starter")
    plan = PLANS.get(plan_name)
    if not plan:
        return jsonify({"error": "Invalid plan"}), 400

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": plan["price_id"], "quantity": 1}],
            mode="subscription",
            success_url=data.get("success_url", "https://leadscore.ai/success?session_id={CHECKOUT_SESSION_ID}"),
            cancel_url=data.get("cancel_url", "https://leadscore.ai/pricing"),
            metadata={"plan": plan_name, "email": data.get("email", "")}
        )
        return jsonify({"checkout_url": session.url, "session_id": session.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe events -- auto-provision tenants on checkout completion."""
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except Exception:
            return jsonify({"error": "Invalid signature"}), 400
    else:
        event = json.loads(payload)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})

        # Auto-create tenant
        api_key = generate_api_key()
        tenants[api_key] = {
            "name": meta.get("name", ""),
            "email": meta.get("email", session.get("customer_email", "")),
            "plan": meta.get("plan", "starter"),
            "custom_criteria": None,
            "leads": [],
            "usage_this_month": 0,
            "month": datetime.utcnow().strftime("%Y-%m"),
            "stripe_customer_id": session.get("customer"),
            "created": datetime.utcnow().isoformat()
        }
        # In production: send welcome email with API key here
        print(f"[NEW TENANT] {meta.get('email')} -> {api_key}")

    return jsonify({"status": "ok"})


# --- Docs Page ---
DOCS_HTML = """<!DOCTYPE html>
<html><head><title>LeadScore AI - API Docs</title>
<style>
body{font-family:monospace;background:#0a0a0f;color:#e2e8f0;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.7}
h1{color:#818cf8}h2{color:#6366f1;margin-top:40px}
code{background:#1e1e2e;padding:2px 8px;border-radius:4px;font-size:.9rem}
pre{background:#1e1e2e;padding:16px;border-radius:8px;overflow-x:auto;margin:12px 0}
.endpoint{background:#16161f;border:1px solid #1e1e2e;border-radius:8px;padding:16px;margin:12px 0}
.method{background:#6366f1;color:#fff;padding:2px 8px;border-radius:4px;font-size:.8rem;font-weight:700}
.method.get{background:#22c55e}
</style></head><body>
<h1>LeadScore AI - API Documentation</h1>
<p>Base URL: <code>https://your-app.railway.app</code></p>
<p>Authentication: Pass your API key via <code>X-API-Key</code> header.</p>

<h2>Score a Lead</h2>
<div class="endpoint">
<span class="method">POST</span> <code>/api/score</code>
<pre>{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "phone": "555-123-4567",
  "service": "Dental Implants",
  "insurance": "PPO",
  "notes": "Looking to schedule within 2 weeks"
}</pre>
</div>

<h2>Webhook (for forms)</h2>
<div class="endpoint">
<span class="method">POST</span> <code>/webhook/&lt;your-api-key&gt;</code>
<p>No auth header needed. Point your form's webhook URL here. Accepts JSON or form-encoded.</p>
</div>

<h2>Get Leads</h2>
<div class="endpoint">
<span class="method get">GET</span> <code>/api/leads?priority=HOT&min_score=70&sort=score_desc&page=1</code>
</div>

<h2>Usage Stats</h2>
<div class="endpoint">
<span class="method get">GET</span> <code>/api/usage</code>
</div>

<h2>Create Checkout</h2>
<div class="endpoint">
<span class="method">POST</span> <code>/api/checkout</code>
<pre>{"plan": "starter", "email": "clinic@example.com"}</pre>
</div>
</body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true")
