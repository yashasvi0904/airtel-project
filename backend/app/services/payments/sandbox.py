"""Built-in test payment gateway. Development/demo only - refuses to start when ENVIRONMENT=production.

It is not a mock that flips a flag: it reproduces the shape of real Indian payment flows so the whole workflow (pending
states, polling, redirects, OTP, expiry, webhooks, retries) is exercised exactly as it would be against a live PSP.

  UPI       collect request: the customer "approves in their UPI app" a few seconds later; or a UPI intent/QR link.
            Test VPAs:  <anything>@bank -> approved | fail@bank -> declined | lowbalance@bank -> insufficient funds
                        timeout@bank -> never approved (the attempt expires)
  Net banking  redirect to a (sandbox) bank page where the customer authorises, declines or abandons.
  Card      3-D Secure OTP step. Test cards:  4111 1111 1111 1111 -> OTP 123456 -> paid
                                              5555 5555 5555 4444 -> paid without OTP
                                              4000 0000 0000 0002 -> declined | 4000 0000 0000 9995 -> insufficient funds
                                              4000 0000 0000 0069 -> expired card
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from ...config import get_settings
from .base import BANK_NAMES, Gateway, GatewayError, GatewayResult, WebhookEvent, aware, card_problem, mask_card, mask_vpa, to_rupees, valid_vpa

OTP = "123456"
MAX_OTP_ATTEMPTS = 3
CARDS = {
    "4111111111111111": ("otp", None, None),
    "5555555555554444": ("frictionless", None, None),
    "4000000000000002": ("declined", "card_declined", "Your bank declined this card. Please try another card or payment method."),
    "4000000000009995": ("declined", "insufficient_funds", "The card has insufficient funds. Please try another card or payment method."),
    "4000000000000069": ("declined", "card_expired", "The bank reports this card as expired. Please use a different card."),
}
VPA_OUTCOMES = {
    "fail": ("failed", "upi_declined", "The payment was declined in your UPI app. You can retry or choose another method."),
    "lowbalance": ("failed", "insufficient_funds", "Your bank account has insufficient balance for this payment."),
}


def hint_block() -> dict:
    """Shown in the checkout UI while the sandbox is active so testers know what to type."""
    return {
        "upi": ["any valid UPI ID (e.g. ravi@okhdfc) is approved after a few seconds", "fail@okhdfc is declined", "lowbalance@okhdfc has insufficient funds",
                "timeout@okhdfc is never approved and expires"],
        "netbanking": ["you are sent to a sandbox bank page where you can authorise, decline or abandon"],
        "card": ["4111 1111 1111 1111 - OTP 123456 - paid", "5555 5555 5555 4444 - paid, no OTP", "4000 0000 0000 0002 - declined",
                 "4000 0000 0000 9995 - insufficient funds", "4000 0000 0000 0069 - expired card", "any future expiry, any 3-digit CVV (4 for Amex)"],
    }


class SandboxGateway(Gateway):
    name = "sandbox"

    def __init__(self):
        s = get_settings()
        if s.environment.lower() == "production":
            raise RuntimeError("The sandbox payment gateway must not be used in production. Set PAYMENT_GATEWAY=razorpay and its keys.")
        self.settings = s

    # -------------------------------------------------------- create
    def create(self, payment, req: dict) -> GatewayResult:
        ref = "sbx_" + secrets.token_hex(10)
        method = payment.method
        if method == "upi":
            return self._create_upi(payment, req.get("upi") or {}, ref)
        if method == "netbanking":
            code = (req.get("netbanking") or {}).get("bank", "")
            if code not in BANK_NAMES:
                raise GatewayError("Please choose your bank from the list.")
            return GatewayResult(
                "pending", ref, details={"bank": BANK_NAMES[code], "bank_code": code}, private={"scenario": "awaiting_bank"},
                next_action={"type": "redirect", "url": f"/pay/bank?payment={payment.id}&ref={ref}", "bank": BANK_NAMES[code],
                             "message": f"Taking you to {BANK_NAMES[code]} to authorise the payment..."})
        if method == "card":
            return self._create_card(payment, req.get("card") or {}, ref)
        raise GatewayError("Unsupported payment method", "unsupported")

    def _create_upi(self, payment, upi: dict, ref: str) -> GatewayResult:
        if upi.get("flow") == "intent":
            url = "upi://pay?" + urlencode({"pa": self.settings.merchant_vpa, "pn": self.settings.merchant_name, "am": f"{to_rupees(payment.amount_paise):.2f}",
                                            "cu": "INR", "tn": f"Order {payment.order_id}", "tr": ref}, quote_via=quote)
            return GatewayResult("pending", ref, details={"flow": "intent"}, private={"scenario": "success"},
                                 next_action={"type": "upi_intent", "intent_url": url, "message": "Open your UPI app and complete the payment, or scan the QR code."})
        vpa = (upi.get("vpa") or "").strip()
        if not valid_vpa(vpa):
            raise GatewayError("Enter a valid UPI ID like name@bank.")
        prefix = vpa.split("@")[0].lower()
        scenario = "never" if prefix.startswith("timeout") else next((k for k in VPA_OUTCOMES if prefix.startswith(k)), "success")
        return GatewayResult("pending", ref, details={"vpa": mask_vpa(vpa), "flow": "collect"}, private={"scenario": scenario},
                             next_action={"type": "upi_collect", "message": f"We sent a payment request to {mask_vpa(vpa)}. Approve it in your UPI app."})

    def _create_card(self, payment, card: dict, ref: str) -> GatewayResult:
        number = "".join(ch for ch in str(card.get("number", "")) if ch.isdigit())
        problem = card_problem(number, int(card.get("exp_month") or 0), int(card.get("exp_year") or 0), str(card.get("cvv", "")), self.settings.today)
        if problem:
            raise GatewayError(problem)
        masked = mask_card(number)  # last4 + network only; `number` goes out of scope at the end of this call
        kind, code, message = CARDS.get(number, ("declined", "card_not_supported", "This card is not accepted in the sandbox. Use one of the test cards shown below."))
        if kind == "declined":
            return GatewayResult("failed", ref, details={"card": masked}, failure_code=code, failure_message=message, private={"scenario": "declined"})
        if kind == "frictionless":
            return GatewayResult("succeeded", ref, gateway_payment_id="pay_" + secrets.token_hex(8), details={"card": masked, "authenticated": "frictionless"})
        return GatewayResult("pending", ref, details={"card": masked}, private={"scenario": "otp", "otp_attempts": 0},
                             next_action={"type": "card_otp", "message": "Enter the 6-digit OTP your bank sent to your registered mobile number."})

    # -------------------------------------------------------- lifecycle
    def refresh(self, payment) -> GatewayResult | None:
        scenario = (payment.gateway_data or {}).get("scenario")
        if scenario in ("success", *VPA_OUTCOMES):
            due = aware(payment.created_at) + timedelta(seconds=self.settings.sandbox_settle_seconds)
            if datetime.now(timezone.utc) < due:
                return None
            if scenario == "success":
                return GatewayResult("succeeded", payment.gateway_ref, gateway_payment_id="pay_" + secrets.token_hex(8))
            _, code, message = VPA_OUTCOMES[scenario]
            return GatewayResult("failed", payment.gateway_ref, failure_code=code, failure_message=message)
        return None  # awaiting_bank / otp / never: the customer (or expiry) decides

    def submit_otp(self, payment, otp: str) -> GatewayResult:
        data = dict(payment.gateway_data or {})
        if data.get("scenario") != "otp":
            raise GatewayError("This payment is not waiting for an OTP", "bad_state")
        if hmac.compare_digest(otp.strip(), OTP):
            return GatewayResult("succeeded", payment.gateway_ref, gateway_payment_id="pay_" + secrets.token_hex(8), details={"authenticated": "3ds_otp"})
        attempts = int(data.get("otp_attempts", 0)) + 1
        if attempts >= MAX_OTP_ATTEMPTS:
            return GatewayResult("failed", payment.gateway_ref, failure_code="otp_failed", failure_message="Too many incorrect OTP attempts. Please start the payment again.")
        data["otp_attempts"] = attempts
        raise _WrongOtp(f"That OTP is incorrect. {MAX_OTP_ATTEMPTS - attempts} attempt(s) left.", data)

    def bank_action(self, payment, outcome: str) -> GatewayResult:
        """The sandbox bank page reporting what the customer did there."""
        if (payment.gateway_data or {}).get("scenario") != "awaiting_bank":
            raise GatewayError("This payment is not waiting for the bank", "bad_state")
        if outcome == "authorize":
            return GatewayResult("succeeded", payment.gateway_ref, gateway_payment_id="pay_" + secrets.token_hex(8))
        if outcome == "decline":
            return GatewayResult("failed", payment.gateway_ref, failure_code="bank_declined", failure_message="Your bank declined the transaction. Please try again or use another method.")
        return GatewayResult("failed", payment.gateway_ref, failure_code="customer_abandoned", failure_message="You left the bank page before finishing. You can retry the payment.")

    # -------------------------------------------------------- webhooks (signed with PAYMENT_WEBHOOK_SECRET)
    @staticmethod
    def sign(raw_body: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()

    def verify_webhook(self, headers: dict, raw_body: bytes) -> bool:
        got = headers.get("x-sandbox-signature", "")
        return bool(got) and hmac.compare_digest(got, self.sign(raw_body, self.settings.payment_webhook_secret))

    def parse_webhook(self, headers: dict, data: dict) -> WebhookEvent | None:
        status = {"payment.succeeded": "succeeded", "payment.failed": "failed"}.get(data.get("event", ""))
        if not status or not data.get("event_id"):
            return None
        amount = data.get("amount")
        return WebhookEvent(str(data["event_id"]), data.get("gateway_ref"), status, int(amount) if amount is not None else None,
                            data.get("failure_code"), data.get("failure_message"), data.get("gateway_payment_id"))


class _WrongOtp(GatewayError):
    """A wrong OTP: the attempt stays pending but the attempt counter must be saved."""

    def __init__(self, message: str, new_private: dict):
        super().__init__(message, "otp_incorrect")
        self.new_private = new_private


def sandbox_webhook_body(event: str, payment, secret: str) -> tuple[bytes, dict]:
    """Test/dev helper: a correctly signed webhook delivery for `payment`."""
    body = json.dumps({"event_id": "evt_" + secrets.token_hex(8), "event": event, "gateway_ref": payment.gateway_ref, "amount": payment.amount_paise}).encode()
    return body, {"x-sandbox-signature": SandboxGateway.sign(body, secret), "content-type": "application/json"}
