# LeadScore AI - Deploy Protocol

## Deployed URLs

| Component | URL |
|-----------|-----|
| **API (Railway)** | https://leadscore-ai-app-production.up.railway.app |
| **Landing Page (GitHub Pages)** | https://hulkmode85.github.io/leadscore-ai-landing/ |
| **API Docs** | https://leadscore-ai-app-production.up.railway.app/docs |
| **App Repo** | https://github.com/Hulkmode85/leadscore-ai |
| **Landing Repo** | https://github.com/Hulkmode85/leadscore-ai-landing |

## Environment Variables (Railway)

| Variable | Status | Notes |
|----------|--------|-------|
| `ANTHROPIC_API_KEY` | SET (placeholder) | Replace with real Anthropic API key |
| `FLASK_SECRET` | SET | Production secret key |
| `ADMIN_KEY` | SET | `ls-admin-prod-7f3x9k2m` |
| `STRIPE_SECRET_KEY` | NOT SET | Add after Stripe setup |
| `STRIPE_WEBHOOK_SECRET` | NOT SET | Add after webhook config |
| `STRIPE_STARTER_PRICE` | NOT SET | Add Stripe price ID |
| `STRIPE_PRO_PRICE` | NOT SET | Add Stripe price ID |
| `STRIPE_AGENCY_PRICE` | NOT SET | Add Stripe price ID |

---

## Steps to Go Live Tonight

### 1. Set Real Anthropic API Key (5 min)
- Go to Railway dashboard > leadscore-ai > Variables
- Replace `ANTHROPIC_API_KEY` with your real key from https://console.anthropic.com/settings/keys
- Service auto-redeploys on variable change

### 2. Verify API is Running (2 min)
```bash
curl https://leadscore-ai-app-production.up.railway.app/
# Should return: {"service":"LeadScore AI","version":"1.0.0",...}
```

### 3. Set Up Stripe (15 min)
See "Stripe Setup" section below.

### 4. Test End-to-End (5 min)
```bash
# Create a test tenant
curl -X POST https://leadscore-ai-app-production.up.railway.app/admin/tenants \
  -H "X-Admin-Key: ls-admin-prod-7f3x9k2m" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Clinic","email":"test@example.com","plan":"starter"}'
# Returns: {"api_key":"ls_xxxx...","plan":"starter"}

# Score a lead with the returned API key
curl -X POST https://leadscore-ai-app-production.up.railway.app/api/score \
  -H "X-API-Key: ls_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane Smith","email":"jane@test.com","phone":"555-1234","service":"Dental Implants","insurance":"PPO","notes":"Need this done ASAP"}'
```

### 5. Custom Domain (Optional, 10 min)
See "Custom Domain Setup" section below.

### 6. Landing Page is Already Live
- https://hulkmode85.github.io/leadscore-ai-landing/
- Demo form hits the live API automatically

---

## Stripe Setup

### Create Products and Prices

1. Go to https://dashboard.stripe.com/products
2. Create 3 products:

**Product 1: LeadScore AI Starter**
- Price: $49/month (recurring)
- Copy the price ID (starts with `price_`)

**Product 2: LeadScore AI Pro**
- Price: $99/month (recurring)
- Copy the price ID

**Product 3: LeadScore AI Agency**
- Price: $199/month (recurring)
- Copy the price ID

### Add Price IDs to Railway
In Railway dashboard > Variables, add:
```
STRIPE_SECRET_KEY=sk_live_your_key_here
STRIPE_STARTER_PRICE=price_xxxxx
STRIPE_PRO_PRICE=price_xxxxx
STRIPE_AGENCY_PRICE=price_xxxxx
```

### Set Up Stripe Webhook
1. Go to https://dashboard.stripe.com/webhooks
2. Add endpoint: `https://leadscore-ai-app-production.up.railway.app/stripe/webhook`
3. Select event: `checkout.session.completed`
4. Copy the webhook signing secret
5. Add to Railway: `STRIPE_WEBHOOK_SECRET=whsec_xxxxx`

### Test Stripe Flow
1. Use Stripe test mode first (sk_test_ key)
2. Create a checkout session:
```bash
curl -X POST https://leadscore-ai-app-production.up.railway.app/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"plan":"starter","email":"test@clinic.com"}'
```
3. Open the returned checkout_url and complete with test card 4242424242424242
4. Verify tenant auto-created in admin endpoint

---

## Custom Domain Setup

### For the API (Railway)
1. Railway dashboard > leadscore-ai > Settings > Domains
2. Add custom domain: `api.leadscore.ai` (or your domain)
3. Add CNAME record in your DNS: `api.leadscore.ai` -> `leadscore-ai-app-production.up.railway.app`
4. Wait for SSL cert (automatic, ~5 min)

### For the Landing Page (GitHub Pages)
1. Go to https://github.com/Hulkmode85/leadscore-ai-landing/settings/pages
2. Add custom domain: `leadscore.ai` (or your domain)
3. Add DNS records:
   - A records: 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
   - Or CNAME: `www.leadscore.ai` -> `hulkmode85.github.io`
4. Enable "Enforce HTTPS"

---

## Pricing

| Plan | Price | Lead Scores/mo | Clinics | Key Features |
|------|-------|----------------|---------|--------------|
| **Starter** | $49/mo | 500 | 1 | Webhook, Dashboard, CSV Export |
| **Pro** | $99/mo | 2,000 | 3 | Custom Criteria, Zapier, Conversion Tracking |
| **Agency** | $199/mo | 10,000 | Unlimited | White-label, API, Custom Integrations |

All plans include 14-day free trial. No contracts.

---

## First 10 Customer Acquisition Plan

### Week 1: Warm Outreach (Target: 3 signups)
1. **Dental clinic Facebook groups** - Post value-first content: "We built a free tool that scores your website leads so your front desk calls the best ones first. Happy to let 10 clinics try it free for 2 weeks."
2. **Reddit r/dentistry, r/dentalschool, r/smallbusiness** - Share the demo, ask for feedback
3. **Direct outreach to 50 dental clinics** - Find clinics on Google Maps with contact forms, send personalized email: "I noticed your website has a contact form. What if every submission got an instant quality score so your staff knew who to call first?"

### Week 2: Content + Cold Outreach (Target: 4 signups)
4. **LinkedIn posts** - "We analyzed 10,000 dental leads. 73% of clinics call them in the wrong order. Here's the data." Link to landing page.
5. **Cold email campaign** - Use Apollo.io or Hunter.io to find dental office managers. Send 3-email sequence focused on the problem (missed high-value leads).
6. **Partner with a dental marketing agency** - Offer them the Agency plan free for 30 days in exchange for referring their clients.

### Week 3: Expand + Optimize (Target: 3 signups)
7. **Chiropractic / medspa / veterinary clinics** - Same pitch, different niche. Reuse all materials.
8. **Typeform / Jotform integration directory** - List LeadScore AI as an integration partner.
9. **Case study from Week 1 users** - "Clinic X increased callback speed by 4x and closed 30% more leads."
10. **AppSumo / Product Hunt launch prep** - Build waitlist for a launch deal ($99 lifetime for first 50 users).

### Metrics to Track
- Landing page visits -> demo completions -> trial signups -> paid conversions
- Cost per acquisition (target: <$20)
- Trial-to-paid rate (target: >25%)
- Monthly churn (target: <5%)

### Quick Wins Available Today
- Post in 3 Facebook groups tonight
- Send 20 cold emails via Gmail (personalized, not bulk)
- Share demo link on Twitter/X with a screen recording
- DM 10 dental clinic Instagram accounts

---

## Architecture Notes

- **Storage**: Currently in-memory (dict). For production persistence, add Redis or Postgres.
- **Recommendation**: Add Railway Postgres plugin when first paying customer signs up.
- **Scaling**: Gunicorn with 2 workers handles ~100 concurrent requests. Scale workers via Procfile.
- **Monitoring**: Check Railway logs dashboard for errors.
- **Backup**: API keys and tenant data are lost on redeploy (in-memory). Priority upgrade: add database.
