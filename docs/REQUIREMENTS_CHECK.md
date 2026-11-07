# Requirements check against the case PDF (Airtel_SYNC_Case.pdf)

Legend: ✅ done and exercised · 🟡 done with a stated limit · ⬜ not done. Nothing is marked ✅ without a test or a run (see [TESTING.md](TESTING.md)).

## The problem statement
"Discover the right bundle, buy it and get it activated with minimal human effort - on a phone, in their preferred language."

| Part | Status | Evidence |
|---|---|---|
| Discover (no salesperson) | ✅ | Advisor chat/voice, [ADVISOR.md](ADVISOR.md) |
| Buy | ✅ | Quote with toggles → checkout → UPI / net banking / card (sandbox gateway) |
| Activated with minimal human effort | 🟡 | KYC auto-verified; only mismatches go to a human review queue. The final "activation" is an admin action standing in for the field/installation partner |
| On a phone | ✅ | Mobile-first UI; `e2e/phone_audit.py`, `e2e/journey.py --mobile` |
| In their preferred language | 🟡 | 10 languages (what the leads' preferred_language column contains). Machine translations, no native-speaker review |

## Key questions

| # | Question | Where answered | Status |
|---|---|---|---|
| 1 | Segments to prioritise first; bundle, price, contract per segment | [BUSINESS_CASE.md](BUSINESS_CASE.md) §2-3 (from the 5,000-lead analysis in [DATA_ANALYSIS.md](DATA_ANALYSIS.md) and the engine's real quotes) | ✅ |
| 2 | Needs discovery without a salesperson (chat/voice, Hindi + regional, few questions, clear monthly price) | Working advisor; BUSINESS_CASE §4 | ✅ chat + voice, 10 languages |
| 3 | Near-instant KYC, DPDP-compliant | Working KYC (OCR, GSTIN/Udyam lookup, consent screen); BUSINESS_CASE §5; [PRIVACY.md](PRIVACY.md) | 🟡 OCR + registries done; **DigiLocker and e-sign are described as roadmap, not built** |
| 4 | Role of field force and channel partners | BUSINESS_CASE §6; admin "Advisor leads" and "Propensity" views hand unclosed leads to them | ✅ as a proposal + back-office view; no partner portal |
| 5 | 3-5 metrics and targets | BUSINESS_CASE §7 (baselines from Appendix A1, e.g. 7% activation, 17.6 days, ₹15,000 acquisition cost); the admin Overview computes the funnel metrics from the data | ✅ |

## Build challenge ("at least")

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| Advisor | GenAI assistant asking type, size, locations, current tools; recommends from the catalogue, explains why in plain language | ✅ | Gemini live; offline rules fallback; Claude provider written, **never run**. Guardrail rejects ungrounded amounts/products |
| Quote & checkout | One transparent monthly price; add-ons the owner can toggle | ✅ | Monthly, setup, GST (18% is a labelled assumption), contract term repricing, add/remove products, dependency repair |
| Smart KYC | Upload with extraction and validation; mocked GSTIN and Udyam lookups; clear consent screen | ✅ | 47 specimens, all 12 applicants asserted; planted problems caught; consent recorded before upload |
| Tracker | Order status the owner can check | ✅ | Orders list and detail with timeline, KYC state, install slot |

## Stretch goals

| Goal | Status | Note |
|---|---|---|
| Voice front end | ✅ | In the advisor, with browser speech + server-transcription fallback; tested with a fake mic and synthesized speech, **not with a human on a real phone** |
| WhatsApp front end | ⬜ | Not built. The advisor engine is channel-independent (`start`/`turn`), so a WhatsApp webhook is a thin adapter |
| Back-office view of leads the advisor could not close | ✅ | Admin → Advisor leads |
| Propensity score | ✅ | Admin → Propensity (a simple model fitted on the supplied leads; see DATA_ANALYSIS and `services/analytics.py`) |

## What teams submit

| Deliverable | Status | File |
|---|---|---|
| 1. Working prototype: code repository | ✅ | `backend/`, `frontend/` (run with `scripts/dev.ps1`) |
| 1. Working prototype: demo video, 3 min max | ⬜ | **Needs a human to record.** Script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| 2. Architecture diagram | ✅ | `docs/architecture.png` / `.svg` |
| 3. Business case, 10 slides or fewer | ✅ | `docs/Udyam_Digital_Business_Case.pptx` (10 slides; check it once in PowerPoint) |
| 4. One-page privacy and security note | ✅ | `docs/Privacy_Note.pdf` (1 page, built from PRIVACY.md) |

## Data provided - how each file is used
- `product_catalogue.csv`: the only source of products, price ranges, setup fees, contract minimums, eligibility and dependencies.
- `smb_leads.csv`: segmentation, funnel baselines, propensity, admin analytics.
- `mock_gstin_registry.csv`, `mock_udyam_registry.csv`: the mock lookup APIs behind onboarding and KYC.
- `kyc_documents/`: OCR and validation test set (the "judges" 15 advisor scenarios and answer key were not supplied to us, so they are not tested).

## Honest gaps, in priority order
1. Demo video (human task).
2. WhatsApp front end, DigiLocker, e-sign: not built.
3. Translations are machine-made; speech tested without a human voice; Anthropic provider and PostgreSQL never run; Razorpay never live; no refunds or recurring billing.
4. "Activation" is simulated by an admin step, not a real provisioning system.
5. Only synthetic data was used; KYC thresholds were tuned on the 47 specimens, so unseen real documents may behave differently.
