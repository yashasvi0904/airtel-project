# Implementation plan and milestones

Status legend: ✅ done and tested · 🟡 done, partly tested · ⬜ not built. Detailed evidence is in [PROGRESS.md](PROGRESS.md) and [TESTING.md](TESTING.md).

| # | Milestone | Deliverable | Exit check | Status |
|---|---|---|---|---|
| 1 | Dataset & brief analysis | `docs/DATA_ANALYSIS.md`; ZIPs extracted to `assignment/` (originals untouched); every CSV profiled; 47 KYC images reviewed and OCR-probed | funnel reproduces the PDF; setup fees reconcile to catalogue for 368 leads | ✅ |
| 2 | Project structure & environment | `backend/`, `frontend/`, `.env.example`, `requirements.txt`, compose, scripts | app boots from clean checkout | ✅ |
| 3 | Backend foundation | config, models, auth, catalogue seeding from CSV, error handling | import + API tests | ✅ |
| 4 | Catalogue engine | eligibility, dependencies, recommender (3 tiers), pricing | 26 rule tests | ✅ |
| 5 | AI advisor | provider interface, slot extraction (EN/HI), question plan, grounding guard, Anthropic + rules providers | 8 advisor tests + live chat runs; Claude path unexercised | 🟡 |
| 6 | Quote & checkout | preview/repricing, quote snapshot, order id, simulated payment | API flow tests, browser E2E | ✅ |
| 7 | Smart KYC | OCR, parsing, registries, matching, pipeline, consent, encryption, retention, erasure | 12 specimen applicants asserted; upload validation tests | ✅ |
| 8 | Order tracking | state machine, slots, tracker, admin advance | API flow + browser E2E | ✅ |
| 9 | Admin dashboard | KPIs, funnel, segments, leads + propensity, orders, KYC queue, advisor leads | API tests; screens rendered in browser | 🟡 (charts verified visually on the Overview tab only) |
| 10 | Integration & bug-fixing | desktop + mobile browser journey; fixes found during runs | `e2e/journey.py` passes on both viewports | ✅ |
| 11 | Documentation & submission pack | README, CLAUDE.md, docs/*, architecture diagram, 10-slide business case, privacy note, demo script | files present, deck renders | ✅ |

## Out of scope / roadmap (named in the case, not built)
Voice or WhatsApp front end · DigiLocker and e-sign · real payment gateway · regional languages beyond Hindi without an LLM key · partner portal with commissions · proper job queue for OCR · Redis rate limiting · PostgreSQL in CI.
