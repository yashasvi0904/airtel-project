# Payments

UPI, net banking and card, behind one gateway interface. **Sandbox** (built in, development only) and **Razorpay** (production) are the two adapters. The customer-facing workflow, the state machine and every safety rule are the same for both.

## Customer workflows

| Method | What the customer sees | Ends when |
|---|---|---|
| **UPI - collect** | Enter `name@bank` (validated) -> "we sent a request to ra\*\*@okhdfc, approve it in your UPI app" with a live countdown | the PSP reports approved / declined / the attempt expires |
| **UPI - intent / QR** | A QR code and an "Open UPI app" `upi://pay?...` link carrying the amount and our reference | the PSP reports the payment; the page updates by itself |
| **Net banking** | Choose a bank -> redirected to the bank -> authorise there -> returned to the order | the bank authorises, declines, or the customer abandons |
| **Card** | Card form (live validation, Luhn, expiry, CVV) -> 3-D Secure OTP step | OTP verified / declined / 3 wrong OTPs |

Every attempt has a 15-minute window (`PAYMENT_EXPIRY_MINUTES`). A refresh or a return from the bank resumes the same attempt. Failed attempts show *why* and that no money was taken, and can be retried; an attempt can be cancelled to switch method. The order page lists every attempt with its receipt number.

## State machine (`services/payments/service.py`)

```
created -> pending -> succeeded
              |-> failed | expired | cancelled
expired | cancelled -> succeeded      (late capture: the customer WAS charged)
failed, succeeded : final
```
`order.payment_status`: `pending` (nothing started) -> `processing` (an attempt is live) -> `paid` | `failed`. **The only code path that sets `paid` is the `succeeded` transition.**

## Guarantees (each one has a test in `backend/tests/test_payments.py`)

| Rule | How |
|---|---|
| The client can never choose the amount | computed server-side from the saved quote (`first_payment`), stored as integer **paise**, never a float |
| No double submit / double charge | `Idempotency-Key` header -> same attempt returned; one live attempt per order (409 `payment_in_progress` carries the attempt id so the UI resumes it); a paid order refuses new attempts |
| Card data is never kept | PAN/CVV exist only inside the one gateway call and are not stored, logged, put in events or returned - only `network + last4`. VPAs are stored/returned masked. Verified by a test that greps the DB rows, events and API output for the digits. With Razorpay the card is typed into *their* window, so it never reaches this server at all |
| A forged "paid" is impossible | Razorpay: HMAC signature on `order_id\|payment_id` **and** we re-fetch the payment from Razorpay and check order id, amount, currency and status ourselves. Webhooks: HMAC over the raw body, constant-time compare, 401 otherwise |
| Webhook retries are safe | every event id is stored with a unique constraint; a repeat is acknowledged as `duplicate` and not re-applied |
| Amount tampering | a webhook whose amount differs from the payment is rejected, the order stays unpaid, and an order event flags it for review |
| A lost webhook can't strand a customer | polling a pending payment reconciles with the gateway before answering |
| Late money is honoured | a success arriving after expiry/cancel marks the order paid (with a note); a *second* success for an already-paid order is flagged `duplicate_charge` + an order event for refund |
| Sandbox can't reach production | `SandboxGateway()` raises when `ENVIRONMENT=production` |
| Payments are private | owner-scoped, 404 (not 403) for other users; endpoints rate-limited (20/min/IP) |
| Installation needs payment | `schedule` still returns 409 `payment_required` until paid |

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/payments/methods` | gateway name, methods, bank list, expiry, sandbox test hints |
| `POST /api/orders/{id}/payments` + `Idempotency-Key` | start an attempt: `{method:"upi", upi:{flow:"collect"\|"intent", vpa}}`, `{method:"netbanking", netbanking:{bank}}`, `{method:"card", card:{number,exp_month,exp_year,cvv,name}}` -> payment with `next_action` |
| `GET /api/payments/{id}` | status (reconciles with the gateway, applies expiry) |
| `GET /api/orders/{id}/payments` | attempts, newest first |
| `POST /api/payments/{id}/otp` `{otp}` | card 3-D Secure step (sandbox) |
| `POST /api/payments/{id}/confirm` | hosted checkout (Razorpay): browser reports `razorpay_order_id/payment_id/signature` |
| `POST /api/payments/{id}/cancel` | abandon a live attempt |
| `POST /api/payments/webhook/{gateway}` | gateway notifications (signature-verified) |
| `POST /api/payments/sandbox/{ref}/bank` | the sandbox "bank page" (exists only with the sandbox gateway) |

`next_action.type`: `upi_collect`, `upi_intent` (`intent_url`), `redirect` (`url`), `card_otp`, `hosted_checkout` (Razorpay options, no secrets).

## Sandbox (default; `PAYMENT_GATEWAY=sandbox`)
Behaves like a real PSP - asynchronous, with redirects, OTP and expiry - and settles lazily by time, so there are no background workers.
- UPI: any valid ID is approved after `SANDBOX_SETTLE_SECONDS` (3); `fail@bank` declined; `lowbalance@bank` insufficient funds; `timeout@bank` never approved (expires).
- Net banking: sandbox bank page with *authorise / decline / close*.
- Cards: `4111 1111 1111 1111` + OTP `123456` paid; `5555 5555 5555 4444` paid without OTP; `4000 0000 0000 0002` declined; `...9995` insufficient funds; `...0069` expired card. Any future expiry, any CVV.

## Going live with Razorpay

```
PAYMENT_GATEWAY=razorpay
ENVIRONMENT=production
RAZORPAY_KEY_ID=rzp_live_...        # or rzp_test_... first
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...         # the secret you set on the webhook in the Razorpay dashboard
```
1. In the Razorpay dashboard add a webhook to `https://<your-domain>/api/payments/webhook/razorpay` for **`payment.captured`** and **`payment.failed`** (Razorpay retries with the same event id; we de-duplicate).
2. Serve over HTTPS only. Keep the key secret on the server; the browser receives only the public `key_id` and the order id.
3. **Run it with test-mode keys first** and walk each method (Razorpay's test UPI/net-banking/card values) before enabling live keys.
4. Review `PAYMENT_EXPIRY_MINUTES` and the rate limiter (it is in-memory: move to Redis if you run more than one worker).

## What is NOT done - read before calling this production-ready
- **The Razorpay adapter has never been run against Razorpay.** No merchant keys were available. It is built from Razorpay's documented API (orders, payments, capture, signature, webhooks) and covered by tests that fake Razorpay's HTTP responses, so request shapes, signature maths and our decisions are verified, but real-world behaviour (field names in edge cases, your account's auto-capture setting, webhook payloads) is not.
- **Refunds are not implemented.** Duplicate or mistaken charges are *detected and flagged* (`duplicate_charge`, order events) but must be refunded from the gateway dashboard.
- **Only the first payment (month 1 + setup) is collected.** Recurring billing for the following months (UPI AutoPay / e-mandate / card-on-file under RBI rules) is not built.
- No GST tax invoice / receipt PDF is generated (a receipt *number* is recorded per attempt).
- No scheduled reconciliation job against the gateway's settlement report (individual payments reconcile on poll/webhook).
- Hosted-checkout front end (loading Razorpay's `checkout.js`, opening the window) is written but untested without keys; the sandbox front end is browser-tested.
- Payments for admin-created or cancelled orders, partial payments and wallets are out of scope.
- Rotate `PAYMENT_WEBHOOK_SECRET` (sandbox) and never reuse dev secrets in production.
