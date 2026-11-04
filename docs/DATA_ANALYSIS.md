# Dataset analysis

All data is synthetic (per the pack README). Originals live untouched in `assignment/data/`; the app only reads them.

## Files and relationships
| File | Rows | Key | Links |
|---|---|---|---|
| `product_catalogue.csv` | 25 | `product_id` (P01-P25) | referenced by `smb_leads.products_of_interest`, `bundle_products`, and by `requires_one_of` inside the catalogue |
| `smb_leads.csv` | 5,000 (40 cols) | `lead_id` | `gstin` -> registry, `udyam_number` -> registry, products -> catalogue |
| `mock_gstin_registry.csv` | 3,534 | `gstin` | one row per lead with `has_gstin = Y` (3,534) |
| `mock_udyam_registry.csv` | 2,723 | `udyam_number` | one row per lead with `has_udyam = Y` (2,723) |
| `kyc_documents/` | 47 PNG | `K01-K12` + type | 12 applicants x 4 docs, minus K05's Udyam certificate = 47 |

Integrity checks (all pass, see `tests/test_business_rules.py`): every lead GSTIN/Udyam exists in its registry; every registry GSTIN passes the 15-character structure and mod-36 checksum (4th PAN character is `X`, accepted); for the 368 activated leads `one_time_setup_inr == sum(qty x catalogue setup fee)` exactly, and `monthly_bundle_value_inr` correlates 0.997 with `sum(qty x mid-price)` (ratio 0.85-1.13 -> prices vary inside the range).

## Catalogue rules that drive the engine
- `available_city_tiers` (P03 tier 1 only), `min_employees` (P03: 5, P05: 10, P06: 25, P10/P21/P24: 10, P12: 3), `min_sites` (P10: 3), `requires_gstin` (P03, P05, P06, P10, P12-P15, P21, P24) -> `eligibility.py`.
- `requires_one_of`: P09, P10, P11, P12, P21, P22, P23 need a connectivity product in the same bundle -> `dependency_status()` and one-click fixes in the UI.
- `min_contract_months` (1, 6, 12, 24) -> allowed contract terms; `typical_install_days` (1-30) -> order tracker and install slots.
- Units differ (per site, line, user, device, camera, counter, vehicle, channel, IP, number, pack, account), so quantities are derived per unit (`default_quantity`). Activated bundles confirm this: P01/P02/P09/P10 quantity up to 12 (= sites), P16 up to 19 (= users), P23 up to 24 (cameras).

## Funnel (Apr-Jun 2026) - matches the case PDF
5,000 leads -> 3,406 contacted (68%) -> 1,974 needs assessed (58%) -> 861 quote accepted (44%) -> 588 KYC complete (68%) -> 368 activated (63%). **7.36% lead-to-activation**, 17.6 days, 3.0 chase calls, CAC ~₹15,053 per activation.

Where the drops are (drop reasons by stage):
| Stage | Biggest reasons | Product answer |
|---|---|---|
| Lead | Unreachable after 3 attempts (805), wrong number (319), not interested (470) | self-serve entry that doesn't need a phone reach |
| Contacted | Owner had no time for a visit (531), locked in (325), only wanted mobile (280), visit not scheduled (296) | no visit: chat advisor; mobile-only path |
| Needs assessed | **Price too high (414)**, competitor cheaper (207), **quote too complex (206)**, **quote took too long (179)** | instant quote with plain-language reasons, budget fitting, transparent GST |
| Quote accepted | **Missing GST/Udyam doc (94)**, **paperwork too long (79)**, **signatory not available (53)**, **docs did not match (47)** | Smart KYC: instant OCR + registry checks, tells the owner exactly what to fix |
| KYC complete | **Installation delayed >21 days (98)**, cancelled before install (53), site not feasible for fibre (41), first payment failed (28) | install slots from typical_install_days, 5G fallback (P04), payment retry |

## Segments (derived by `analytics.segments()`)
| Segment | Share of leads | Conversion | Avg bundle/mo | 6-mo churn | NPS | Days | Acq. spend per activation* | Payback (months of MRR) |
|---|---|---|---|---|---|---|---|---|
| Micro retail & services | 54.2% | 4.1% | ₹2,505 | 22.7% | 7.0 | 16.6 | ~₹20,000 | ~8.0 |
| Professional offices | 24.9% | 11.1% | ₹6,796 | 13.8% | 6.9 | 16.9 | ~₹10,700 | ~1.6 |
| Small multi-site | 15.1% | 11.0% | ₹31,233 | 10.8% | 6.7 | 18.8 | ~₹15,600 | ~0.5 |
| Small manufacturers | 5.8% | 12.8% | ₹19,980 | 8.1% | 6.5 | 20.5 | ~₹15,300 | ~0.8 |
\* total acquisition cost of the segment's leads / its activations.

## Signals worth acting on
- **GSTIN is the strongest single signal: 9.6% activation with vs 2.0% without** (also 10 of 25 products need it). Onboarding asks for it first and verifies it instantly; the bundle page explains which products a GSTIN unlocks.
- Lead source: Referral 14.8%, Inbound call 9.5%, Channel partner 8.0%, Field sales 7.3%, Website 4.3%, WhatsApp 2.8%. But cost per activation: Field sales ~₹24k, Channel partner ~₹21k vs Website ~₹6.4k, WhatsApp ~₹4.0k, Referral ~₹4.1k -> digital + referral is far cheaper per activation; field/partners earn their cost on large accounts.
- Current setup: leased-line users convert at 15%, "mixed per site" 12.7% vs mobile-hotspot users 4.5% -> hotspot users are the micro mass market and need the most guidance.
- Tier 1 converts 8.6% vs tier 2 6.1%. Language: Hindi/English ~8%, Tamil 4.3%, Punjabi 4.2%, Kannada 5.1% -> regional-language advisor is a growth lever (needs the LLM provider).
- Fast activation is not a churn risk, long activations are: churn 22% for >25 days vs 13-15% for 10-25 days (the <=10-day bucket has only 7 customers, too small to read).
- Customers who chase status more often score lower NPS (7.5 at <=1 call -> 6.0 at 5+ calls) -> the tracker removes the cause.
- Suspended GSTINs activate at 4.0%; **cancelled GSTINs show 10.8% (n=167)** - counter-intuitive, so the product never trusts the lead file: it checks the registry status and blocks GSTIN-only products when the status is not Active.

## Data quirks found
- 847 of 9,971 `products_of_interest` entries are ineligible for that lead under the catalogue rules (8.5%) - customers ask for things they cannot buy, so the advisor must explain *why* and what unlocks it (done via `Eligibility.unlock`).
- 40 of 1,651 purchased product lines violate eligibility and 9 violate a dependency (noise in the synthetic history). The engine does not copy history; it only uses *attach rates* as a ranking signal.
- The same business name appears in several cities/legal forms (e.g. six "Vindhya Tours & Travels" GSTINs). KYC therefore keys on GSTIN/Udyam number, never on name alone.
- The Udyam number is **not printed** on any specimen certificate (the field is blank). Udyam verification uses the applicant's entered number if given, else a name + city + state lookup.
- Certificate dates (registration) differ between documents and registries for most applicants, so they are not used as a signal (would create false alarms).

## KYC specimen findings (K01-K12), verified by running the pipeline
| ID | Finding | Pipeline outcome |
|---|---|---|
| K01 | GSTIN 37IHK... is **Cancelled**; no Udyam record exists for the enterprise | rejected (`gstin_cancelled`, `udyam_not_found`) |
| K02 | Certificate scanned at a ~7° tilt | deskewed, read, verified |
| K03, K08, K09, K10, K12 | clean | verified |
| K04 | GST certificate heavily blurred (Laplacian variance ~1 vs ~1,000-1,900 for the rest) | action_required: re-upload (`unreadable_document`) |
| K05 | **Udyam certificate missing** (3 of 4 documents) | incomplete (`missing_document`) |
| K06 | GSTIN digit altered (…S**8**189… vs registry …S**5**189…): checksum fails | rejected (`gstin_invalid`) with "looks altered - closest registered number 08\*\*\*1ZO" |
| K07 | GST legal name says "(Prop. **Shri** Physio Clinic)", registry/other documents say "Neelgiri Physio Clinic" | needs_review (`gst_legal_name_mismatch`) |
| K11 | Utility bill dated 2025-10-31, 257 days before 2026-07-15 | action_required (`address_proof_stale`) |

There is no official answer key in the student pack; these outcomes come from reading the images and registries by hand and are asserted in `tests/test_kyc.py`.

## Propensity model (stretch goal)
Logistic regression on lead profile only (segment, source, tier, turnover, GSTIN/Udyam, current internet, language, log employees/sites/spend). Hold-out AUC **0.68** - modest but honest (no funnel-stage leakage). Top drivers: segment (micro -, multi-site +), GSTIN (+), referral source (+), WhatsApp-campaign/website sources (-). Used to rank the re-engagement list and the "unclosed advisor journeys" call list.
