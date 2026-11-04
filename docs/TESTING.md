# Testing

Everything below was actually run in this repository's environment (Windows 11, Python 3.12, Node 24, Chromium via Playwright). "Not tested" items are listed explicitly at the end.

## Automated backend tests - `cd backend && .venv/Scripts/python -m pytest -q`
**84 tests** (80 plus 4 Google sign-in tests added later; the API/advisor files were re-run and pass, the full suite was last run in full at 80) (full run ≈ 3.5 minutes; most of the time is OCR on the 47 specimen images and the 4 KYC upload flows).

| File | Tests | What is covered |
|---|---|---|
| `tests/test_business_rules.py` | 26 | GSTIN structure + mod-36 checksum for **all 3,534 registry GSTINs**; tampered-digit detection; OCR-confusion repair; Udyam format; segment/tier inference; eligibility (tier, employees, sites, GSTIN: active / declared / cancelled / missing); dependencies; selection validation (every error code); pricing stays inside catalogue ranges for all 25 products × terms × quantities; longer term never costs more; GST/setup/first-payment/contract arithmetic; **setup fees reproduce `one_time_setup_inr` for 60 activated leads**; term options; recommender never offers an ineligible product and always satisfies dependencies in all tiers for 4 archetypes; GSTIN gating of SD-WAN; 5G fallback; budget handling; per-unit quantities |
| `tests/test_kyc.py` | 19 | The **12 specimen applicants** end to end (OCR → parse → registries → checks): K02, K03, K08, K09, K10, K12 verified; K01 rejected (cancelled GSTIN + unknown Udyam); K02 rotated scan straightened; K04 blurry → re-upload; K05 missing Udyam → incomplete; K06 tampered GSTIN rejected with nearest-registered hint; K07 legal-name mismatch → needs_review; K11 stale bill (257 days); identifiers masked in the report; required-document policy; name/address fuzzy matching; Udyam lookup by details; non-image rejection |
| `tests/test_api_flow.py` | 27 | Health/meta/catalogue; onboarding derivation and 5 invalid-input cases; advisor conversation to recommendation; recommendations vs eligibility; **dynamic repricing (24 months cheaper than 12)**, dependency errors with fixes, ineligible product, bad quantity, unknown journey; invalid selections never saved; auth required to order; order id format and idempotency; other customers get 404 / admin routes 403 / 401; payment failure then success, double payment 409; scheduling blocked before payment/KYC; consent required before upload; invalid/unknown/oversized uploads (422); wrong document type flagged; full KYC → verified → scheduling → installing → activated with all tracker steps; erasure removes documents; admin dashboards (funnel counts 5000/3406/1974/861/588/368, segment set, lead filtering, AUC > 0.6); mock registry lookups; Hindi greeting; **manual-review path** (needs_review blocks scheduling until an admin approves; non-admin cannot decide); **rejected identity never unlocks scheduling**; replacing a failing document re-verifies; **retention purge deletes encrypted files and extracted data** |
| `tests/test_advisor.py` | 8 | English and Hindi slot extraction, short answers in context, budget/priority phrases, garbage input, question plan terminates and skips known slots, merge ignores invalid values, **grounding guard rejects invented ₹ amounts and product ids** |

## Google sign-in
Backend: 4 tests with Google's tokeninfo response mocked (sign-up, repeat sign-in reuses the account, link to an existing email account, wrong audience / unverified email / wrong issuer / bad token rejected, disabled without a client ID). Browser: the login and register pages show the real Google button when a client ID is configured and a disabled "not configured" button otherwise. **Not tested: a real Google sign-in** - it needs your OAuth client ID and a real Google account.

## Browser end-to-end - `python e2e/journey.py [--mobile]` (backend :8000 + frontend :3000 running)
Drives real Chromium through: landing → onboarding (live GSTIN lookup) → advisor chat → bundle (switch 12→24 months and assert the price changes) → checkout (register, confirm order, **failed then successful simulated payment**) → KYC consent (button disabled until ticked) → specimen upload (K03) → verified with checks visible → slot booking → tracker. Also fails on any page error, console error or HTTP 5xx.
- Desktop (1280×900): **passed**. Mobile (390×844): **passed**. A K07 run correctly stopped at "needs review".
- `python e2e/admin.py`: sign-in guard for signed-out visitors, admin login, all six tabs render real data, no console/HTTP errors - **passed**.
- `python e2e/bundle_fix.py`: removing broadband while CCTV is selected shows the dependency card and disables checkout; one click on **Add** repairs it; GSTIN entry unlocks GSTIN-only products - **passed**.
- Static checks: `tsc --noEmit`, `eslint src`, `next build` - clean.
- Screenshots of the landing, advisor, bundle, KYC and tracker pages (desktop and mobile) and admin Overview/Segments were reviewed by eye; bugs found that way (chart animation/scale, truncated KPI text, duplicate KYC events, sticky-header overlap in full-page captures is a screenshot artefact) were fixed.

## Findings from testing that changed the product
- OCR dropped the GSTIN value on most certificates and the Udyam number is blank on all of them → crop-and-retry OCR, checksum-based repair, Udyam lookup by name+city+state.
- The first K07 comparison passed (fuzzy ratio 0.91 on the whole legal name) → legal names are now compared as proprietor and business parts separately.
- An early recommender dropped a customer's explicit request (billing) from the Starter bundle when over budget → asked-for products now survive in every tier.
- Duplicate "KYC incomplete" timeline events per upload → one event per status change.

## Not tested / known limits
- **Claude (Anthropic) provider**: written to the documented SDK (structured outputs, `effort: low`) but never called - no API key was available. Failures fall back to rules, which *is* tested via the guard and `MockProvider`; a live key may need prompt tuning.
- **PostgreSQL**: not available locally; only SQLite was run.
- **KYC accuracy beyond the supplied specimens**: tuned and asserted on 47 synthetic, clean-ish images; real phone photos, PDFs and other utility bills are untested. K04's blurry certificate is reported as unreadable rather than recovered.
- The deck was verified structurally (10 slides, text-fit estimate, geometry, wireframe render) - **no PowerPoint/LibreOffice was available to render it**, so open it once before submitting.
- Hindi: the landing page renders correctly on a phone-width viewport (screenshot reviewed) and the advisor greeting/questions are asserted in tests; the comparison card, onboarding field labels and pages after the advisor are English only.
- No load/performance, security-penetration or accessibility-audit testing (labels, roles, focus rings and contrast were considered but not audited with a tool).
