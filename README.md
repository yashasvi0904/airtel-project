# Udyam Digital - Accel Business

AI-assisted, digital-first onboarding for small businesses: **advisor -> bundle & live quote -> checkout -> Smart KYC -> order tracking**, plus a back-office dashboard. Built for the Airtel SYNC / YTL Hackathon 2026, Track A (*Project Udyam Digital*).

[![Solution architecture and data flows](docs/Architecture_Flow.png)](docs/Architecture_Flow.pdf)

## Demo video (3 minutes)

▶ **[Watch the demo video](docs/demo_video.mp4)**

> Opens GitHub's built-in video player. If it does not play in your browser, click **Download raw file** on that page.

## What's in the box
| Capability | Where |
|---|---|
| Landing page, onboarding, AI advisor chat (EN/HI) | `frontend/src/app/{page,onboarding,advisor}` |
| Recommendation with eligibility + dependencies, optional add-ons, live repricing | `/bundle`, `backend/app/services/{eligibility,recommender,pricing}.py` |
| Quote & checkout, order id | `/checkout`, `backend/app/services/orders.py` |
| 10 languages + phone-first UI (voice, sticky checkout bar, 44 px targets) | `frontend/src/lib/{i18n,locales}`, `backend/app/services/i18n.py`, [docs/LOCALIZATION.md](docs/LOCALIZATION.md) |
| Payments: UPI, net banking, card | `/orders/{id}/pay`, `backend/app/services/payments/`, [docs/PAYMENTS.md](docs/PAYMENTS.md) |
| Smart KYC: consent, OCR, GSTIN & Udyam lookup, name/address match, missing/invalid/mismatch detection | `/orders/[id]/kyc`, `backend/app/services/kyc/` |
| Order tracker, installation slots, activation | `/orders`, `/orders/[id]` |
| Admin: funnel, segments, leads + propensity, orders, KYC queue, unclosed advisor leads | `/admin` |

Deliverables: [solution architecture & data flows (PDF)](docs/Architecture_Flow.pdf) · [data workflow (PDF)](docs/Data_Workflow.pdf) · [business case deck (10 slides)](docs/Udyam_Digital_Business_Case.pptx) · [1-page data privacy & security note (PDF)](docs/Privacy_Note_1page.pdf) · [3-minute demo script](docs/DEMO_SCRIPT.md).

## Architecture, data workflow and privacy

### Solution architecture and data flows
[![Solution architecture and data flows](docs/Architecture_Flow.png)](docs/Architecture_Flow.pdf)

Red outline = deterministic business logic (the source of truth) · blue = AI (interprets and phrases only) · grey = data · dashed = external service. The nine numbered flows (owner message -> catalogue engine -> advisor wording -> LLM guard -> order -> payment -> KYC -> activation -> admin analytics) are listed under the diagram. [Open the PDF](docs/Architecture_Flow.pdf).

### Data workflow: how data is converted and processed
[![Data workflow](docs/Data_Workflow.png)](docs/Data_Workflow.pdf)

Four lanes: **A** reference data (CSVs -> typed records, analytics, attach rates, propensity model) · **B** advice and quote (words -> needs -> bundle -> price -> explanation) · **C** order to activation (quote -> order -> payment -> install slot -> activated) · **D** Smart KYC (upload -> OCR -> parse -> validate and look up -> match -> verdict). [Open the PDF](docs/Data_Workflow.pdf).

### Data privacy and security note (1 page)
The data pack is synthetic, but it is treated as real personal data under the **DPDP Act, 2023**.
- **Consent first**: a dedicated consent screen (purposes, retention, right to delete) comes before any document upload; a customer can decline and verify through the field team instead.
- **Minimal collection**: exactly four KYC documents, asked only after consent. OCR runs on our own server, so documents never go to a third party or to the AI provider.
- **Identifiers are masked** in every API response, screen and log, and encrypted in the database. Files are encrypted at rest (Fernet/AES) under random names.
- **30-day retention**: documents and extracted data are purged automatically, and the customer can delete them and withdraw consent at any time. Only the KYC outcome stays as the audit record.
- **AI is guarded**: it only receives typed text, a short history and catalogue facts, and any reply containing a rupee amount or product the engine did not produce is dropped. Prices, eligibility and KYC verdicts are rule-based.
- **Humans stay in the loop**: borderline KYC cases go to a reviewer; every rejection states the reason and the fix.
- **Known gaps** are listed honestly in the note (single-process rate limiter, encryption key derived from the JWT secret unless `ENCRYPTION_KEY` is set, no DPIA / breach workflow / DigiLocker yet).

[Read the full 1-page note (PDF)](docs/Privacy_Note_1page.pdf) · [PRIVACY.md](docs/PRIVACY.md)

## Quick start (Windows or macOS/Linux)
Prerequisites: Python 3.12 (3.11-3.13 work; **not 3.14** - no onnxruntime wheels), Node 20+.

```bash
# 1. backend
cd backend
py -3.12 -m venv .venv                      # macOS/Linux: python3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp ../.env.example ../.env                  # optional: add ANTHROPIC_API_KEY, change secrets
.venv/Scripts/python -m uvicorn app.main:app --port 8000

# 2. frontend (new terminal)
cd frontend
npm install
npm run build && npm run start              # or: npm run dev
# open http://localhost:3000
```
`scripts/dev.ps1` (Windows) / `scripts/dev.sh` start both. The dataset is read from `assignment/data/` (override with `DATA_DIR`). First start seeds the catalogue and an admin user (`admin@accel.example` / `ChangeMe!123` - change in `.env`).

### Without an API key
The advisor works offline using a built-in keyword extractor (English/Hindi/Hinglish) and deterministic templates ("Offline rules mode" badge in the chat). With `ANTHROPIC_API_KEY` set, Claude interprets free-form answers (structured output) and rephrases the engine's reply; pricing, eligibility and KYC are identical either way. **The Claude path is implemented but was not exercised during development (no key available).**

### Sign in / Sign up with Google (optional)
Create an OAuth client ID (type *Web application*) in Google Cloud Console, add your site URL under *Authorised JavaScript origins*, and set `GOOGLE_CLIENT_ID` in `.env` (and in the Render service). The login and register pages then show Google's button; the ID token is verified on the server and an account is created on first use. Without it the button is shown disabled and email + password still works.

### PostgreSQL
```bash
docker compose up -d db
# .env:  DATABASE_URL=postgresql+psycopg://udyam:udyam@localhost:5432/udyam
```
Schema is portable (SQLAlchemy, JSON columns), but only SQLite was run in testing.

## Trying the demo
1. Onboarding: e.g. *Dental clinic, Pune, 14 staff, ₹12,000 budget*, GSTIN `29HLDXH5566X1ZB` (active in the mock registry).
2. Advisor: answer the questions (or tap the chips), say "recommend".
3. Bundle: toggle products, switch 12 -> 24 months, watch the price change; try removing broadband while keeping CCTV to see the dependency fix.
4. Checkout: create an account, confirm, pay (sandbox: UPI ID `fail@okhdfc` is declined; card `4111 1111 1111 1111` + OTP `123456` succeeds; see docs/PAYMENTS.md).
5. KYC: give consent, then use **"Demo: use a specimen applicant"** to load K01-K12 from the supplied pack (K03 verifies cleanly; K07 -> manual review; K01 cancelled GSTIN; K06 tampered GSTIN; K11 stale bill; K04 blurry; K05 missing Udyam).
6. Book the installation slot. Sign in as admin to advance the order (installing -> activated) and see the dashboards.

## Tests
```bash
cd backend && .venv/Scripts/python -m pytest -q          # unit + API + KYC on the 12 specimen applicants
backend/.venv/Scripts/python e2e/journey.py              # browser E2E (servers running); add --mobile
```
Results and limitations: [docs/TESTING.md](docs/TESTING.md).

## Docs
[CLAUDE.md](CLAUDE.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [API](docs/API.md) · [DATA_ANALYSIS](docs/DATA_ANALYSIS.md) · [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) · [PROGRESS](docs/PROGRESS.md) · [PRIVACY](docs/PRIVACY.md) · [TESTING](docs/TESTING.md) · [BUSINESS_CASE](docs/BUSINESS_CASE.md)

## Known limitations (honest list)
Payments: sandbox gateway only, Razorpay adapter never run live, no refunds / recurring billing · no DigiLocker / e-sign / WhatsApp front end (voice is built) · Claude provider untested · PostgreSQL untested · only Hindi + English UI copy · KYC tuned on the 47 synthetic specimens (real-world scans will need more OCR hardening) · in-memory rate limiter (single process) · GST rate and price-position policy are assumptions.

## Live deployment (Vercel + Render)
- Frontend: https://udyam-digital.vercel.app (Vercel project `udyam-digital`, root `frontend/`). It proxies `/api/*` to `BACKEND_URL`, which is baked in at build time.
- Backend: `render.yaml` + `Dockerfile.backend` (Render free web service `udyam-digital-api`). Push the repo to GitHub, then Render > New > Blueprint. The admin password is generated; read it under the service's Environment tab. If Render gives the service a different URL, update Vercel and redeploy:
  `cd frontend && npx vercel env rm BACKEND_URL production -y; echo -n https://<your-service>.onrender.com | npx vercel env add BACKEND_URL production; npx vercel deploy --prod`
- Free-tier caveats: the service sleeps when idle (first request ~30-60 s), and its SQLite data resets on restart/redeploy. The Docker image has not been built locally (no Docker here).
