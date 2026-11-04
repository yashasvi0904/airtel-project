# API reference

Base URL `http://localhost:8000` (or `/api/*` via the Next.js proxy). Interactive docs: `/docs` (Swagger). Auth: `Authorization: Bearer <jwt>`. Errors are `{"detail": "..."}`; conflicts use `{"detail": {"code": "...", "message": "..."}}`.

| Status | Meaning |
|---|---|
| 401 | sign in required / bad token | 
| 403 | admin only (or another user's journey) |
| 404 | not found - also returned for other users' orders |
| 409 | state conflict (e.g. scheduling before KYC) |
| 422 | validation error, readable message |
| 429 | rate limited |

## Public
| Method & path | Purpose |
|---|---|
| `GET /api/health` | liveness |
| `POST /api/auth/register` `{email,name,password(>=8),phone?}` | create customer, returns `{token,user}` |
| `POST /api/auth/login` `{email,password}` | `{token,user}` |
| `GET /api/auth/config` | `{google_client_id}` (public; null when Google sign-in is not configured) |
| `POST /api/auth/google` `{credential}` | Google Identity Services ID token → verified server-side (audience = our client ID, issuer, `email_verified`); creates the customer on first use, links to an existing account with the same email; returns `{token,user,created}` |
| `GET /api/auth/me` | current user |
| `GET /api/meta` | cities (tier, state), business types -> segment, connectivity options, languages, segment benchmarks |
| `GET /api/catalogue` | the 25 products as loaded from the CSV |
| `GET /api/public/stats` | landing-page proof points from the dataset |
| `GET /api/registry/gstin/{gstin}` | mock GST lookup: format, checksum, `found`, status, names, address |
| `GET /api/registry/udyam/{number}` | mock Udyam lookup |
| `GET /api/demo/kyc-samples`, `GET /api/demo/kyc-samples/{K01}/{doc}` | specimen KYC images for the demo loader |

## Journey (guest allowed; id is the capability; locked to the owner after checkout)
| Method & path | Purpose |
|---|---|
| `POST /api/journeys` `ProfileIn` | onboarding: `business_name, business_type, city, employees, sites, current_internet, monthly_budget?, monthly_telecom_spend?, has_gstin, gstin?, has_udyam, contact_name?, phone?, language`. Returns journey with derived `segment`, `city_tier`, `gstin_status`, and `propensity` (0-100) |
| `GET /api/journeys/{id}` | journey (GSTIN masked) |
| `PATCH /api/journeys/{id}/profile` | add GSTIN / change size or budget (re-validates, clears selection) |
| `POST /api/journeys/{id}/advisor/start` | first assistant message (idempotent; returns history if resumed) |
| `POST /api/journeys/{id}/advisor/message` `{text}` | `{reply, question, chips, recommendation_ready, provider, summary?}` |
| `GET /api/journeys/{id}/advisor` | chat history |
| `GET /api/journeys/{id}/recommendations?term_months=` | `{recommendation:{tiers:{starter,recommended,complete} each {items[{reasons,quantity}], term_months, quote}, recommended_tier, over_budget, excluded[{eligibility.reasons, unlock}], notes}, catalogue:[25 with eligibility]}` |
| `POST /api/quotes/preview` `{journey_id, items[{product_id,quantity}], term_months}` | stateless re-pricing: `{valid, errors[{code,message,product_id}], fixes[{add_one_of, or_remove}], quote}` |
| `PUT /api/journeys/{id}/selection` | validate + save selection |
| `POST /api/journeys/{id}/quote` | freeze a quote snapshot (422 if invalid, 409 if nothing selected) |
| `GET /api/quotes/{id}` | quote lines + totals |

Quote `totals`: `monthly_subtotal, monthly_gst, monthly_total, setup_subtotal, setup_gst, setup_total, first_payment, term_months, contract_value, list_monthly_subtotal, discount_vs_list, gst_rate_percent, install_days, term_options, required_term_months, current_monthly_spend?, vs_current_spend?`.

Error codes in `validate_selection`: `empty, unknown_product, duplicate, quantity, ineligible, dependency, term`.

## Orders (customer, owner-scoped)
| Method & path | Purpose |
|---|---|
| `POST /api/orders` `{quote_id, accept_terms}` | place order -> `UD-YYYYMMDD-XXXXXX` (idempotent per quote) |
| `GET /api/orders`, `GET /api/orders/{id}` | list / detail with `tracker.steps`, `tracker.next_action`, `events`, `items`, `totals` |
| `POST /api/orders/{id}/pay` `{method: upi\|card\|netbanking, simulate: success\|fail}` | simulated payment |
| `GET /api/orders/{id}/slots`, `POST /api/orders/{id}/schedule` `{date,window}` | install slots; requires paid + KYC verified/approved |

## Smart KYC (customer)
| Method & path | Purpose |
|---|---|
| `GET /api/orders/{id}/kyc` | case: consent, required documents, uploads (with purge dates), declared (masked), result, notice text |
| `POST /api/orders/{id}/kyc/consent` `{accepted, has_gstin, has_udyam, gstin?, udyam_number?}` | records consent (notice version, purposes, retention) |
| `POST /api/orders/{id}/kyc/documents` multipart `doc_type, file` | validates, OCRs, re-verifies the whole case, returns result. `doc_type`: `gst_certificate, udyam_certificate, signatory_id, address_proof` |
| `POST /api/orders/{id}/kyc/verify` | re-run verification |
| `DELETE /api/orders/{id}/kyc` | erase files + extracted data, withdraw consent |

Result: `{status: verified|needs_review|action_required|incomplete|rejected, summary, required_documents, document_status, checks[{id,label,status,detail,doc}], issues[{code,severity,doc,message,action}], next_actions, registry:{gstin,udyam}, documents:{type:{fields(masked),quality,status}}}`.

## Admin (`role=admin`)
| Method & path | Purpose |
|---|---|
| `GET /api/admin/overview` | baseline KPIs from the dataset + live platform counters |
| `GET /api/admin/funnel` | funnel, drop reasons by stage, weekly trend |
| `GET /api/admin/segments` | segment table + product attach rates |
| `GET /api/admin/breakdown/{source,language,gstin,tier,internet,turnover,city,business_type}` | conversion/CAC/value per dimension |
| `GET /api/admin/leads?page&size&segment&source&stage&q&sort&open_only` | leads with propensity percentile |
| `GET /api/admin/propensity` | model AUC and weights |
| `GET /api/admin/orders`, `POST /api/admin/orders/{id}/advance` `{to,note}` | list; `installing`, `activated`, `cancelled` with transition rules |
| `GET /api/admin/kyc`, `POST /api/admin/kyc/{order}/decision` `{approve,note}` | KYC queue; manual review of `needs_review` |
| `GET /api/admin/advisor-leads` | advisor journeys that never became orders, ranked by propensity |
| `POST /api/admin/maintenance/purge-documents` | delete expired document files |
