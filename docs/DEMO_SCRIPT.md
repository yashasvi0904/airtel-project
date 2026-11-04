# 3-minute demo script

Setup: backend on :8000, frontend on :3000, fresh browser window on a phone-width viewport for the first 20 seconds, then desktop. Keep the admin dashboard open in a second tab. Have **K03** and **K07** ready in the KYC sample loader.

| Time | Screen | Say | Do |
|---|---|---|---|
| 0:00-0:15 | Landing (phone width) | "Small businesses buy telecom one product at a time: a 3-5 day quote, paper KYC, 17.6 days to activate and three chase calls. Udyam Digital does it in one sitting - and this is the real app, not a mock-up." | Show the 'Today vs Udyam Digital' card; tap **Build my plan**. |
| 0:15-0:35 | Onboarding | "A dental clinic in Pune, 14 people, 12 thousand rupee budget. Entering the GSTIN checks it instantly against the registry - GSTIN holders convert at 9.6% versus 2%, and 10 of the 25 products need one." | Fill the form, paste `29HLDXH5566X1ZB`, the green 'Found: … Active' appears. Continue. |
| 0:35-1:05 | Advisor | "The advisor asks only what it needs, in English or Hindi. The AI reads the owner's words; it never picks a price." | Chips: 'Internet keeps going down' → 'CCTV' (type '4 cameras, WhatsApp, email') → 'Yes, fibre is available' → '5' → 'recommend'. Point at the reasons per product and the budget line. |
| 1:05-1:35 | Bundle | "Every line comes from the catalogue with eligibility and dependencies checked. Watch the price." | Switch 12 → 24 months (price drops, 'you save'). Remove Biz Fibre 300 - CCTV turns red with a one-click fix; click **Add**. Open 'Browse all other products': tier-1-only and GSTIN-only items explain why and what unlocks them. Click **Get quote & checkout**. |
| 1:35-1:50 | Checkout | "One transparent price: monthly with GST, setup, contract, total." | Create account, accept, **Confirm order** (note the order id), tick 'simulate failed payment' once, then pay. |
| 1:50-2:30 | Smart KYC | "Consent first - purposes, 30-day retention, delete any time. Then four documents." | Give consent. Load **K03**: four documents read, fields masked, registry matched, **Verified**; open 'Show all 21 checks'. Then load **K07**: 'needs a quick manual review - GST legal name says *Shri* Physio Clinic, registry says *Neelgiri*'. Mention K06 (tampered GSTIN digit caught by checksum), K01 (cancelled GSTIN), K11 (stale bill), K04 (blurry), K05 (missing Udyam). |
| 2:30-2:45 | Tracker | "No chasing calls: the owner books the slot and sees every step." | Back to K03 order → **Continue to installation** → book a slot → tracker shows 'Technician visit on …'. |
| 2:45-3:00 | Admin | "For sales and partners: the funnel, which segments pay back fastest, and a propensity-ranked list of journeys the advisor could not close. KPI targets: 7.4% → 11% conversion, 17.6 → ≤ 7 days, 3 → ≤ 1 chase calls, CAC ₹15k → ≤ ₹9k." | Admin tab: Overview funnel, Segments table, Orders (Start installation → Mark activated). |

Fallback if something stalls: the offline rules advisor and the specimen KYC loader need no network or API key. If OCR is slow on the first upload (model warm-up ~3 s), keep talking over it.

Judge-facing notes: prices are inside the catalogue range by a published rule; GST 18% is an assumption; payments are simulated; Claude provider is implemented but this demo runs in offline rules mode unless a key is set.
