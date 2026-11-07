"""Razorpay adapter (Standard Checkout flow).

Why hosted checkout: card numbers, CVVs and OTPs are typed into Razorpay's own form, so they never touch this server
(that is what keeps us out of PCI-DSS card-data scope). Our server only ever sees ids and statuses:

  1. create()   POST /v1/orders with the amount computed server-side           -> order_id, handed to the browser
  2. browser    opens Razorpay Checkout (UPI / net banking / card, pre-selected) -> payment_id + signature
  3. confirm()  verify HMAC_SHA256(order_id|payment_id, key_secret), then GET /v1/payments/{id} and check
                order, amount, currency and status ourselves. A signature alone is not accepted as proof of payment.
  4. webhook    `payment.captured` is the backstop for browsers that closed before step 3.

NOT yet exercised against live Razorpay (no merchant keys were available when this was written): it is covered by unit
tests that fake Razorpay's HTTP responses. Run it with test-mode keys first (see docs/PAYMENTS.md).
"""
import hashlib
import hmac

import httpx

from ...config import get_settings
from .base import Gateway, GatewayError, GatewayResult, WebhookEvent, mask_vpa


class RazorpayGateway(Gateway):
    name = "razorpay"
    API = "https://api.razorpay.com/v1"

    def __init__(self, http: httpx.Client | None = None):
        s = get_settings()
        if not (s.razorpay_key_id and s.razorpay_key_secret):
            raise RuntimeError("PAYMENT_GATEWAY=razorpay needs RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")
        self.s = s
        self.key_id, self._secret = s.razorpay_key_id, s.razorpay_key_secret
        self.http = http or httpx.Client(timeout=15, auth=(self.key_id, self._secret))

    # -------------------------------------------------------- helpers
    def _call(self, method: str, path: str, **kw) -> dict:
        try:
            r = self.http.request(method, f"{self.API}{path}", **kw)
        except httpx.HTTPError as e:  # network: the customer was not charged by this call
            raise GatewayError("The payment provider is not reachable right now. Please try again in a moment.", "gateway_unreachable") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("description", "")
            except ValueError:
                msg = ""
            raise GatewayError(msg or "The payment provider rejected the request.", f"gateway_{r.status_code}")
        return r.json()

    def _sign(self, order_id: str, payment_id: str) -> str:
        return hmac.new(self._secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    # -------------------------------------------------------- create
    def create(self, payment, req: dict) -> GatewayResult:
        order = self._call("POST", "/orders", json={
            "amount": payment.amount_paise, "currency": payment.currency, "receipt": payment.receipt[:40],
            "notes": {"payment_id": payment.id, "order_id": payment.order_id}})
        prefill: dict = {"method": payment.method}
        if payment.method == "netbanking" and (req.get("netbanking") or {}).get("bank"):
            prefill["bank"] = req["netbanking"]["bank"]
        if payment.method == "upi" and (req.get("upi") or {}).get("vpa"):
            prefill["vpa"] = req["upi"]["vpa"]  # prefill only; the customer confirms inside Razorpay
        return GatewayResult("pending", order["id"], details={"method": payment.method}, next_action={
            "type": "hosted_checkout", "key_id": self.key_id, "gateway_order_id": order["id"], "amount": payment.amount_paise,
            "currency": payment.currency, "name": self.s.merchant_name, "description": f"Order {payment.order_id}", "prefill": prefill,
            "message": "Complete the payment in the secure window."})

    # -------------------------------------------------------- confirm / refresh
    def _evaluate(self, payment, rp: dict) -> GatewayResult:
        """Decide from Razorpay's own record (not from anything the browser told us)."""
        if rp.get("order_id") != payment.gateway_ref:
            raise GatewayError("This payment does not belong to this order.", "order_mismatch")
        if int(rp.get("amount", -1)) != payment.amount_paise or rp.get("currency") != payment.currency:
            raise GatewayError("The paid amount does not match this order. Our team has been alerted; you have not been marked as paid.", "amount_mismatch")
        status = rp.get("status")
        if status == "authorized":  # accounts without auto-capture: capture the exact amount now
            rp = self._call("POST", f"/payments/{rp['id']}/capture", json={"amount": payment.amount_paise, "currency": payment.currency})
            status = rp.get("status")
        details = {"method": rp.get("method")}
        if rp.get("method") == "card" and isinstance(rp.get("card"), dict):
            details["card"] = {"network": rp["card"].get("network"), "last4": rp["card"].get("last4")}
        if rp.get("method") == "upi" and rp.get("vpa"):
            details["vpa"] = mask_vpa(rp["vpa"])
        if rp.get("method") == "netbanking":
            details["bank"] = rp.get("bank")
        if status == "captured":
            return GatewayResult("succeeded", payment.gateway_ref, gateway_payment_id=rp["id"], details=details)
        if status == "failed":
            return GatewayResult("pending", payment.gateway_ref, details={**details, "last_failure": rp.get("error_description")},
                                 failure_code=rp.get("error_code"), failure_message=rp.get("error_description"))
        return GatewayResult("pending", payment.gateway_ref, details=details)

    def confirm(self, payment, data: dict) -> GatewayResult:
        order_id, pay_id, sig = data.get("razorpay_order_id", ""), data.get("razorpay_payment_id", ""), data.get("razorpay_signature", "")
        if order_id != payment.gateway_ref or not hmac.compare_digest(sig, self._sign(order_id, pay_id)):
            raise GatewayError("The payment response could not be verified.", "bad_signature")
        return self._evaluate(payment, self._call("GET", f"/payments/{pay_id}"))

    def refresh(self, payment) -> GatewayResult | None:
        if not payment.gateway_ref:
            return None
        items = self._call("GET", f"/orders/{payment.gateway_ref}/payments").get("items", [])
        for rp in items:
            if rp.get("status") in ("captured", "authorized"):
                return self._evaluate(payment, rp)
        return None

    # -------------------------------------------------------- webhooks
    def verify_webhook(self, headers: dict, raw_body: bytes) -> bool:
        secret = self.s.razorpay_webhook_secret
        got = headers.get("x-razorpay-signature", "")
        return bool(secret and got) and hmac.compare_digest(got, hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest())

    def parse_webhook(self, headers: dict, data: dict) -> WebhookEvent | None:
        kind = {"payment.captured": "succeeded", "payment.failed": "attempt_failed"}.get(data.get("event", ""))
        entity = (((data.get("payload") or {}).get("payment") or {}).get("entity")) or {}
        event_id = headers.get("x-razorpay-event-id") or ""
        if not kind or not event_id or not entity:
            return None
        return WebhookEvent(event_id, entity.get("order_id"), kind, entity.get("amount"), entity.get("error_code"), entity.get("error_description"), entity.get("id"))
