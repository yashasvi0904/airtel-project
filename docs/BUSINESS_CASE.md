# Business case (text version of the 10-slide deck)

Deck: [Udyam_Digital_Business_Case.pptx](Udyam_Digital_Business_Case.pptx) (built on the supplied SYNC template by `scripts/build_deck.py`; numbers are computed from the dataset and the product's own engine at build time).

## 1. Target customer and the problem
Owner-run businesses with 1-150 staff in tier 1-2 cities who need connectivity plus a few digital services on one bill. Today (Apr-Jun 2026, 5,000 leads): **7.4%** reach activation, **17.6 days** to activate, **3.0** status-chase calls per customer, **₹15,053** acquisition cost per activation. GSTIN holders activate at **9.6% vs 2.0%**.

## 2. Which segments first (key question 1)
| Segment | Share of leads | Conversion | Bundle/mo | Churn 6m | Months of bundle revenue to repay acquisition cost |
|---|---|---|---|---|---|
| Micro retail & services | 54% | 4.1% | ₹2,505 | 23% | ~8.0 |
| Professional offices | 25% | 11.1% | ₹6,796 | 14% | ~1.6 |
| Small multi-site | 15% | 11.0% | ₹31,233 | 11% | ~0.5 |
| Small manufacturers | 6% | 12.8% | ₹19,980 | 8% | ~0.8 |

**Wave 1** professional offices + multi-site; **Wave 2** manufacturers (field-assisted surveys); **Wave 3** micro retail through a self-serve starter bundle, referral and WhatsApp.

## 3. Bundle, price point, contract per segment (from the product's engine, Pune example, before 18% GST)
| Segment | Example | Bundle | Monthly | Setup | Contract |
|---|---|---|---|---|---|
| Micro | Kirana, 3 staff | Biz Fibre 100 + 2 × Postpaid 299 | ~₹1,917 | ₹0 | 12 (24 cheaper) |
| Professional | Dental clinic, 14 | Fibre 300, 6 SIMs, email × 14, endpoint security × 14, 1 TB backup | ~₹7,765 | ₹0 | 12 (24 cheaper) |
| Multi-site | Restaurants, 5 sites | Fibre 100 × 5, SIMs, failover × 5, SD-WAN × 5, POS × 5, CCTV × 20 | ~₹31,960 | ₹81,000 | 24 |
| Manufacturer | Textile unit, 85 | Leased line 100, SIM, failover, email × 85, endpoint × 50 | ~₹45,783 | ₹16,500 | 24 |
(The deck lists the exact generated bundles; price positions follow `pricing_rules.json`.)

## 4. Needs discovery without a salesperson (key question 2)
A chat (or voice) advisor in the owner's language - ten, the ones the dataset's leads speak - asks only the few questions that matter for that business, chosen by segment and current setup (a hotspot user is not asked what is wrong; a factory is asked about machines, not WhatsApp). It reads what was said, including what the owner does *not* want, says back what it understood, never repeats a question, and explains every product. The engine, not the model, picks products and prices. WhatsApp is the next channel, through the same provider interface. See [ADVISOR.md](ADVISOR.md).

## 5. KYC and DPDP (key question 3)
Consent screen with purposes and retention; four documents only; OCR + GSTIN/Udyam registry + name/address matching; precise fix lists; DigiLocker and e-sign are the next integrations. See [PRIVACY.md](PRIVACY.md).

## 6. Field force and partners (key question 4)
Field cost per activation is ~₹24k (partners ~₹21k) vs ~₹4-6k for referral/inbound/website. Digital takes micro and professional offices end to end; field and partners move up-market (multi-site, manufacturers), run the same advisor in assisted mode, do assisted KYC and installation, and receive the propensity-ranked list of stalled journeys.

## 7. Metrics and targets (key question 5)
| Metric | Baseline | 12-month target |
|---|---|---|
| Lead → activation | 7.4% | ≥ 11% |
| Time to activate (fibre/wireless bundles) | 17.6 days | ≤ 7 days |
| Status-chase calls | 3.0 | ≤ 1 |
| Acquisition cost per activation | ₹15,053 | ≤ ₹9,000 |
| 6-month churn | 15.2% | ≤ 12% |
Guardrails: KYC first-pass ≥ 75% with zero wrongful auto-approvals; NPS ≥ 7.5.

## 8. Value scenario (assumptions, not forecasts)
Stage targets needs-assessed → quote 44% → 50%, quote → KYC 68% → 80%, KYC → activated 63% → 72% give 568 activations per 5,000 leads (+200, +54%). The same acquisition spend (₹55.4 lakh) then costs ~₹9.8k per activation, and each extra ~200-customer cohort adds ~₹24.7 lakh of monthly recurring revenue at today's mean bundle.

## 9. Rollout and risks
Pilot (8 weeks, two cities) → all tier 1-2 cities + manufacturers → micro self-serve. Risks: OCR on real photos, LLM hallucination (guard), DPDP, install capacity, channel conflict, pricing assumptions - each with a mitigation on slide 9.
