"""Gateway interface, shared value objects, input validation and masking helpers for the payment module.

The rule that matters most here: card numbers, CVVs and full UPI IDs are *transient*. They may pass through a
request to the gateway adapter, but they are never stored, logged or returned - only masked display values are.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

METHODS = ("upi", "netbanking", "card")

# (code, display name). Codes follow the NetBanking codes used by Indian payment gateways.
BANKS: list[tuple[str, str]] = [
    ("SBIN", "State Bank of India"), ("HDFC", "HDFC Bank"), ("ICIC", "ICICI Bank"), ("UTIB", "Axis Bank"),
    ("KKBK", "Kotak Mahindra Bank"), ("PUNB", "Punjab National Bank"), ("BARB_R", "Bank of Baroda"),
    ("YESB", "YES Bank"), ("IDFB", "IDFC FIRST Bank"), ("INDB", "IndusInd Bank"), ("CNRB", "Canara Bank"), ("UBIN", "Union Bank of India"),
]
BANK_NAMES = dict(BANKS)

VPA_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]{1,63}@[a-zA-Z][a-zA-Z0-9]{1,31}$")


class GatewayError(Exception):
    """The request cannot be sent to the gateway (bad input, unsupported operation). Nothing was charged."""

    def __init__(self, message: str, code: str = "invalid_request"):
        super().__init__(message)
        self.code = code


@dataclass
class GatewayResult:
    status: str  # pending | succeeded | failed
    ref: str | None = None
    gateway_payment_id: str | None = None
    next_action: dict | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    details: dict = field(default_factory=dict)  # masked, safe to show the customer
    private: dict | None = None  # gateway-side state kept on the payment row, never returned to clients


@dataclass
class WebhookEvent:
    event_id: str
    gateway_ref: str | None
    status: str  # succeeded | failed | attempt_failed
    amount_paise: int | None
    failure_code: str | None = None
    failure_message: str | None = None
    gateway_payment_id: str | None = None


class Gateway:
    """A payment service provider adapter. Subclasses implement what their PSP supports."""
    name = "base"

    def create(self, payment, req: dict) -> GatewayResult:
        raise NotImplementedError

    def refresh(self, payment) -> GatewayResult | None:
        """Ask the PSP for the current state. None = nothing new (still pending)."""
        return None

    def submit_otp(self, payment, otp: str) -> GatewayResult:
        raise GatewayError("This payment does not use an OTP step", "unsupported")

    def confirm(self, payment, data: dict) -> GatewayResult:
        raise GatewayError("This payment is not confirmed this way", "unsupported")

    def cancel(self, payment) -> None:
        return None

    def verify_webhook(self, headers: dict, raw_body: bytes) -> bool:
        return False

    def parse_webhook(self, headers: dict, data: dict) -> WebhookEvent | None:
        return None


# ---------------------------------------------------------------- money

def to_paise(rupees) -> int:
    """Rupees (float/str/Decimal) -> integer paise, rounding half up. Money is never held as a float after this."""
    return int((Decimal(str(rupees)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_rupees(paise: int) -> float:
    return float(Decimal(paise) / 100)


# ---------------------------------------------------------------- time

def aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything here is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- validation + masking

def valid_vpa(vpa: str) -> bool:
    return bool(VPA_RE.match(vpa or ""))


def mask_vpa(vpa: str) -> str:
    name, _, handle = vpa.partition("@")
    return f"{name[:2]}{'*' * max(2, len(name) - 2)}@{handle}"


def luhn_ok(number: str) -> bool:
    if not number.isdigit() or not 12 <= len(number) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def card_network(number: str) -> str:
    if number.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2[2-7])", number):
        return "Mastercard"
    if re.match(r"^3[47]", number):
        return "American Express"
    if re.match(r"^(60|65|81|82|508)", number):
        return "RuPay"
    return "Card"


def card_problem(number: str, month: int, year: int, cvv: str, today: date) -> str | None:
    """A customer-readable reason the card details are unusable, or None. Never includes the digits themselves."""
    if not luhn_ok(number):
        return "That card number is not valid. Please check it and try again."
    if not 1 <= month <= 12:
        return "The expiry month must be between 01 and 12."
    if (year, month) < (today.year, today.month):
        return "This card has expired."
    want = 4 if card_network(number) == "American Express" else 3
    if not (cvv.isdigit() and len(cvv) == want):
        return f"The security code (CVV) must be {want} digits."
    return None


def mask_card(number: str) -> dict:
    return {"network": card_network(number), "last4": number[-4:]}
