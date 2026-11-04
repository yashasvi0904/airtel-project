# CLAUDE.md - Udyam Digital (Accel Business)

Working prototype for the Airtel SYNC / YTL Hackathon 2026 Track A case "Project Udyam Digital": a digital-first journey that lets a small-business owner discover a bundle, buy it, verify KYC and get it activated with minimal human effort.

## Layout
```
assignment/            ORIGINAL material, extracted from the two ZIPs. Read-only - never edit.
  data/                product_catalogue.csv, smb_leads.csv, mock_gstin_registry.csv, mock_udyam_registry.csv, kyc_documents/ (47 PNGs), README.md
  sync/                Airtel_SYNC_Case.pdf (case study), Submission Template_Sync.pptx
6ae1873397bc1_digital/ the original ZIPs as supplied (untouched)
backend/               FastAPI app (app/), tests (tests/), venv (.venv, git-ignored)
frontend/              Next.js 16 + React 19 + TypeScript + Tailwind 4 app
e2e/journey.py         Playwright browser test of the whole customer journey
docs/                  ARCHITECTURE, API, DATA_ANALYSIS, IMPLEMENTATION_PLAN, PROGRESS, PRIVACY, TESTING, DEMO_SCRIPT, BUSINESS_CASE, architecture diagram, slides
scripts/               dev.ps1 / dev.sh, build_deck.py
storage/               runtime only: SQLite db, encrypted uploads, logs (git-ignored)
```

## The architectural rule (do not break it)
The LLM **interprets** the customer's words and **explains** results. Everything that decides a product, a price, an eligibility outcome or a KYC verdict is deterministic Python.
- Eligibility, dependencies, recommendation: `backend/app/services/{eligibility,recommender}.py`
- Pricing: `services/pricing.py` + `app/data/pricing_rules.json` (policy for where a price lands inside the catalogue's min-max range)
- KYC: `services/kyc/*` (OCR -> parsers -> validators/registry/matching -> pipeline). No LLM involved.
- Advisor: `services/advisor/*`. `providers.py` has the `Provider` interface (Anthropic + Mock). `reply_is_grounded()` rejects any LLM reply containing a rupee amount or product id the engine did not produce, falling back to the deterministic template.

## Conventions
- Python 3.12 venv in `backend/.venv` (system default is 3.14, which lacks onnxruntime wheels). Type hints, small modules, no business constants outside CSV/JSON/env.
- Money is `Decimal` inside the engine, serialised as float rupees with 2 decimals.
- Never log or return raw identifiers: use `kyc.matching.mask()`; identifiers and extracted fields are Fernet-encrypted at rest (`services/crypto.py`).
- API errors: `{"detail": "..."}`; 409 for state conflicts (`code` + `message`), 422 for validation, 404 (not 403) for other users' orders.
- Frontend: client components calling same-origin `/api/*` (proxied by `next.config.ts`). Every page has loading, empty and error states. No keys in frontend code.
- Tests are real: `cd backend && .venv/Scripts/python -m pytest` (backend), `python e2e/journey.py` (browser, needs both servers running).
- Don't claim a feature works without running it. See `docs/TESTING.md` for what has and has not been exercised.

## Important decisions / assumptions (details in docs/ARCHITECTURE.md)
1. **"Today" is 2026-07-15** (dataset README) via `REFERENCE_DATE`; used for address-proof age, ID expiry, install slots, order ids.
2. **Price inside [min,max]**: the catalogue only gives ranges. Policy in `pricing_rules.json`: longer term, higher quantity and larger bundles move the price toward the floor. Setup = qty x catalogue setup fee (this reproduces `one_time_setup_inr` for all 368 activated leads).
3. **GST 18%** is not in the catalogue; shown as a clearly-labelled configurable assumption (`GST_RATE_PERCENT`).
4. **Contract term** = one term for the bundle, >= the longest `min_contract_months`; options 12/24 (plus the minimum).
5. **OCR**: RapidOCR (PaddleOCR PP-OCR models on ONNX Runtime). PaddlePaddle itself has no wheels for recent Pythons. The Udyam number is not printed on any specimen certificate, so Udyam is looked up by number (if the applicant enters it) or by enterprise name + city + state.
6. **Database**: SQLite by default, PostgreSQL via `DATABASE_URL` (psycopg installed, `docker-compose.yml` provided). Only SQLite has been exercised here.
7. **Payments are simulated** (success/fail toggle). **LLM**: the Anthropic provider is implemented but could not be exercised without an API key; the rules provider is what was tested.
8. Hindi is supported end-to-end in the advisor (templates) and key UI strings; other Indian languages need the LLM provider.

## Commands
```
scripts/dev.ps1                      # start backend :8000 and frontend :3000 (Windows)
cd backend && .venv/Scripts/python -m pytest -q
cd frontend && npm run build && npm run lint
backend/.venv/Scripts/python e2e/journey.py --shots out/   # browser journey
backend/.venv/Scripts/python scripts/build_deck.py          # regenerate docs/Udyam_Digital_Business_Case.pptx
```
Admin login (dev defaults, change via .env): `admin@accel.example` / `ChangeMe!123`.

## Progress tracking
`docs/PROGRESS.md` is the source of truth for what is done / pending / tested. Update it with every milestone.
