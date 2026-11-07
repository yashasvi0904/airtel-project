# Progress tracker

Last updated: 2026-11-07 (installable PWA; before that advisor v2 + voice rebuild; requirements cross-check in [REQUIREMENTS_CHECK.md](REQUIREMENTS_CHECK.md)). Legend: ✅ done + tested · 🟡 done, partially tested · ⬜ not built.

## Customer journey
| Feature | Status | Evidence |
|---|---|---|
| Landing page (Airtel-inspired branding, services, segments, CTA, EN/HI toggle) | ✅ | browser E2E, screenshots desktop + mobile |
| Business onboarding (name, category, city, employees, sites, connectivity, budget, GSTIN with live registry check) | ✅ | API validation tests (5 bad inputs), E2E |
| **Advisor v2** (adaptive discovery per segment, understands rejections/quantities/link type, context-aware yes/no, "what I understood" echo, never repeats; see [ADVISOR.md](ADVISOR.md)) and **voice** (browser speech, else record + server transcription, visible reason on every failure) | ✅ offline + live Gemini (EN/HI/Hinglish) · ✅ voice chain with synthesized speech in real Chromium · 🟡 no human-voice test on a phone | `test_advisor_dialogue.py` (28), `test_voice.py` (6), `e2e/voice.py`; full suite 226 passed |
| AI advisor chat (follow-ups, uses catalogue data, explains each product, EN/HI/Hinglish) | ✅ rules provider · ✅ Gemini provider (live, free tier) · 🟡 Claude provider | 22 advisor tests (incl. goodbye/greeting handling, LLM guardrails with fake providers, free-form Q&A via `advisor/qa.py`: product/price/setup/contract/GST/process questions answered from catalogue + quote, off-topic gets an honest 'can't answer'), API flow, E2E. Gemini exercised live in a manual chat (Hinglish, free-form, totals); Claude path never executed (no credit) |
| Product recommendation (eligibility, pricing, dependencies, 3 bundle tiers, optional add-ons, ineligible products with unlock hints) | ✅ | 26 rule tests, API tests, `e2e/bundle_fix.py` |
| Quote & checkout (monthly, setup, contract, GST, dynamic repricing, summary, confirmation) | ✅ | API tests, E2E (12→24 months changes price) |
| Smart KYC (consent, upload, OCR, GSTIN + Udyam registry, name/address match, missing/invalid/mismatch detection, explanations) | ✅ on the 47 specimens | 19 KYC tests + 4 API flow tests; 12 applicants asserted |
| Order management (unique id, KYC status, install scheduling, activation, tracker) | ✅ | API flow, E2E |
| **Phone-first + 10 languages** (hi, en, mr, kn, gu, te, ta, bn, pa, ml - the languages the dataset's leads prefer): every customer page translated, language picker + auto-detect + per-script fonts, advisor templates and engine sentences localised without an LLM, voice input/read-aloud (feature-detected), 44 px tap targets, sticky price/checkout bars, Back control | ✅ automated + browser-verified · 🟡 translations are machine-made, no native review | 43 localization tests, `e2e/hindi.py` (Hindi purchase on a phone), `e2e/language_audit.py` (9 languages x 10 pages), `e2e/phone_audit.py`; speech not tested with real audio. See [LOCALIZATION.md](LOCALIZATION.md) |
| **Installable mobile app (PWA)**: web manifest + icons (any/maskable/iOS), service worker (offline page, cached static assets, **never** `/api`), "Install app" banner on the home page + menu entry (Chrome/Edge/Android native prompt; iOS shows Share -> Add to Home Screen steps), `Permissions-Policy` allowing microphone/camera for the site, KYC **Take photo** (opens the phone camera) with in-browser shrinking of big photos | ✅ browser-verified in Chromium (`e2e/pwa.py`, 28 checks) · 🟡 not yet tried on a real Android/iPhone; the native install prompt is simulated in the test (headless Chrome never fires it); needs HTTPS or localhost | `e2e/pwa.py`, `e2e/voice.py` and `e2e/journey.py` re-run on the production build. See [TESTING.md](TESTING.md) |
| Payments: UPI (collect + QR/intent), net banking (bank redirect), card (3-D Secure OTP); attempts, idempotency, expiry, webhooks, reconciliation, duplicate-charge flag | ✅ sandbox gateway (browser-tested) · 🟡 Razorpay adapter (unit-tested against faked HTTP, never run live) | 51 payment tests (`tests/test_payments.py`), browser run of all three methods + failure/retry/resume/mobile. **Not built:** refunds, recurring monthly billing, invoice PDFs. See [PAYMENTS.md](PAYMENTS.md) |
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
