# Progress tracker

Last updated: 2026-11-04 (end of build). Legend: ✅ done + tested · 🟡 done, partially tested · ⬜ not built.

## Customer journey
| Feature | Status | Evidence |
|---|---|---|
| Landing page (Airtel-inspired branding, services, segments, CTA, EN/HI toggle) | ✅ | browser E2E, screenshots desktop + mobile |
| Business onboarding (name, category, city, employees, sites, connectivity, budget, GSTIN with live registry check) | ✅ | API validation tests (5 bad inputs), E2E |
| AI advisor chat (follow-ups, uses catalogue data, explains each product, EN/HI/Hinglish) | ✅ rules provider · 🟡 Claude provider | 8 advisor tests, API flow, E2E. Claude path never executed (no key) |
| Product recommendation (eligibility, pricing, dependencies, 3 bundle tiers, optional add-ons, ineligible products with unlock hints) | ✅ | 26 rule tests, API tests, `e2e/bundle_fix.py` |
| Quote & checkout (monthly, setup, contract, GST, dynamic repricing, summary, confirmation) | ✅ | API tests, E2E (12→24 months changes price) |
| Smart KYC (consent, upload, OCR, GSTIN + Udyam registry, name/address match, missing/invalid/mismatch detection, explanations) | ✅ on the 47 specimens | 19 KYC tests + 4 API flow tests; 12 applicants asserted |
| Order management (unique id, KYC status, simulated payment incl. failure, install scheduling, activation, tracker) | ✅ | API flow, E2E |
| Admin dashboard (lead overview, segmentation, orders, KYC queue + manual review, conversion metrics, charts, propensity, unclosed advisor leads) | ✅ | API tests, `e2e/admin.py`, screenshots (Overview, Segments reviewed; Leads/Orders/KYC/Advisor tabs smoke-tested) |

## Engineering requirements
| Requirement | Status | Note |
|---|---|---|
| Real features, not mock-ups; datasets used, not invented | ✅ | catalogue seeded from CSV; leads/registries read at runtime; originals untouched |
| No hardcoded prices or verification outcomes | ✅ | prices from catalogue + `pricing_rules.json`; KYC from registry/validators. GST 18% and price-position bonuses are config assumptions |
| Frontend/backend separation, env secrets, `.env.example`, no keys in frontend | ✅ | proxy rewrite; key only read in backend |
| Validation, error handling, loading/empty/error states | ✅ | every page; 422 messages; generic 500 |
| Responsive/mobile | ✅ | mobile E2E at 390 px |
| Tests for business logic and APIs | ✅ | 80 backend tests + 3 browser suites |
| Missing key must not break the app | ✅ | offline rules provider; `LLM_PROVIDER=mock` forced in tests |
| Security & authorization | ✅ | JWT, roles, owner-scoped orders, uploads validated, encrypted at rest, rate limits |
| PostgreSQL | 🟡 | supported via `DATABASE_URL` + compose; never run |

## Milestones
1. Dataset analysis ✅ · 2. Structure/env ✅ · 3. Backend foundation ✅ · 4. Catalogue + recommender ✅ · 5. AI advisor 🟡 · 6. Quote/checkout ✅ · 7. KYC ✅ · 8. Order tracking ✅ · 9. Admin ✅ · 10. Integration + bug fixing ✅ · 11. Docs + submission pack ✅

## Submission pack
| Item | File | Status |
|---|---|---|
| Working application + code | `backend/`, `frontend/` | ✅ |
| Architecture diagram | `docs/architecture.png` / `.svg` | ✅ |
| Business case (≤ 10 slides) | `docs/Udyam_Digital_Business_Case.pptx` (+ `BUSINESS_CASE.md`) | ✅ built on the SYNC template; **not opened in PowerPoint** - check it once |
| 1-page privacy note | `docs/PRIVACY.md`, `docs/Privacy_Note.pdf` (1 page) | ✅ |
| 3-minute demo script | `docs/DEMO_SCRIPT.md` | ✅ script; **demo video not recorded** (needs a human to screen-record) |

## Pending / ideas
- Record the 3-minute demo video.
- Try the Claude provider with a real key and tune the prompts (`services/advisor/providers.py`).
- Run against PostgreSQL; move rate limiting to Redis; background job for OCR.
- DigiLocker + e-sign, WhatsApp/voice front end, real payment gateway, more Indian languages, partner portal.
- Harden OCR with real-world scans (photos, PDFs, other utility-bill layouts).
- Replace the placeholder pricing-position policy and GST rate with finance-approved values.
