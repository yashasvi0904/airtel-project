"""Payment orchestration: the attempt state machine, idempotency, expiry, reconciliation and webhooks.

Invariants (each has a test):
  * The amount charged is computed on the server from the saved quote - the client never sends an amount.
  * An order becomes `paid` only through `_transition(... "succeeded")`, i.e. after the gateway (or a verified webhook)
    said so and, for webhooks, the amount matched. Nothing else can set it.
  * One live attempt per order; creating a payment is idempotent on `Idempotency-Key`.
  * Webhook deliveries are authenticated (HMAC) and processed exactly once per gateway event id.
  * A success that arrives after we gave up (expired/cancelled) is honoured - the customer was charged - and a second
    success for an already-paid order is flagged `duplicate_charge` for refund instead of being silently dropped.
  * Card numbers / CVVs / full VPAs are never persisted or logged (see base.py).
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import Order, Payment, PaymentWebhookEvent, Quote
from ..orders import add_event
from .base import BANKS, METHODS, Gateway, GatewayError, GatewayResult, aware, to_paise, to_rupees
from .sandbox import SandboxGateway, _WrongOtp, hint_block

log = logging.getLogger("payments")

ACTIVE = ("created", "pending")
TERMINAL = ("succeeded", "failed", "expired", "cancelled")
ALLOWED = {
    "created": {"pending", "succeeded", "failed", "expired", "cancelled"},
    "pending": {"succeeded", "failed", "expired", "cancelled"},
    "expired": {"succeeded"},    # late capture
    "cancelled": {"succeeded"},  # late capture
    "failed": set(),
    "succeeded": set(),
}
METHOD_LABEL = {"upi": "UPI", "netbanking": "Net banking", "card": "Card"}


class PaymentError(Exception):
    def __init__(self, message: str, code: str = "invalid", payment_id: str | None = None):
        super().__init__(message)
        self.code, self.payment_id = code, payment_id


# ---------------------------------------------------------------- gateway selection

_gateway: Gateway | None = None
_gateway_key: str | None = None


def get_gateway() -> Gateway:
    global _gateway, _gateway_key
    s = get_settings()
    key = f"{s.payment_gateway}:{s.environment}:{bool(s.razorpay_key_id)}"
    if _gateway is None or key != _gateway_key:
        if s.payment_gateway == "razorpay":
            from .razorpay import RazorpayGateway

            _gateway = RazorpayGateway()
        elif s.payment_gateway == "sandbox":
            _gateway = SandboxGateway()
        else:
            raise RuntimeError(f"Unknown PAYMENT_GATEWAY '{s.payment_gateway}' (use sandbox or razorpay)")
        _gateway_key = key
    return _gateway


def reset_gateway() -> None:
    global _gateway, _gateway_key
    _gateway = _gateway_key = None


def methods_view() -> dict:
    gw = get_gateway()
    out = {"gateway": gw.name, "methods": [{"id": "upi", "label": "UPI"}, {"id": "card", "label": "Credit / debit card"}, {"id": "netbanking", "label": "Net banking"}],
           "banks": [{"code": c, "name": n} for c, n in BANKS], "expiry_minutes": get_settings().payment_expiry_minutes,
           "hosted_checkout": gw.name == "razorpay"}
    if gw.name == "sandbox":
        out["sandbox_hints"] = hint_block()
    return out


# ---------------------------------------------------------------- views

def _describe(p: Payment) -> str:
    d = p.details or {}
    if p.method == "upi":
        return d.get("vpa") or "UPI"
    if p.method == "netbanking":
        return d.get("bank") or "Net banking"
    c = d.get("card") or {}
    return f"{c.get('network', 'Card')} ending {c['last4']}" if c.get("last4") else "Card"


def payment_view(p: Payment) -> dict:
    live = p.status in ACTIVE
    return {
        "id": p.id, "order_id": p.order_id, "method": p.method, "method_label": METHOD_LABEL.get(p.method, p.method), "description": _describe(p),
        "amount": to_rupees(p.amount_paise), "amount_paise": p.amount_paise, "currency": p.currency, "status": p.status,
        "next_action": p.next_action if live else None, "failure_code": p.failure_code, "failure_message": p.failure_message,
        "details": {k: v for k, v in (p.details or {}).items() if k != "last_failure" or live},
        "attempt_no": p.attempt_no, "receipt": p.receipt, "gateway": p.gateway,
        "expires_at": aware(p.expires_at).isoformat(), "paid_at": aware(p.paid_at).isoformat() if p.paid_at else None,
        "created_at": aware(p.created_at).isoformat(),
    }


def list_payments(db: Session, order: Order) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at.desc())).all())


# ---------------------------------------------------------------- state machine

def _apply(db: Session, order: Order, p: Payment, r: GatewayResult) -> None:
    if r.ref:
        p.gateway_ref = r.ref
    if r.gateway_payment_id:
        p.gateway_payment_id = r.gateway_payment_id
    if r.details:
        p.details = {**(p.details or {}), **r.details}
    if r.private is not None:
        p.gateway_data = r.private
    if r.next_action is not None:
        p.next_action = r.next_action
    if r.status == "succeeded":
        _transition(db, order, p, "succeeded")
    elif r.status == "failed":
        p.failure_code, p.failure_message = r.failure_code, r.failure_message
        _transition(db, order, p, "failed")
    else:
        if r.failure_message:  # a failed try *inside* a still-open gateway order (customer can retry there)
            p.details = {**(p.details or {}), "last_failure": r.failure_message}
        _transition(db, order, p, "pending")


def _transition(db: Session, order: Order, p: Payment, to: str, note: str = "") -> None:
    if p.status == to:
        return
    if to not in ALLOWED[p.status]:
        raise PaymentError(f"A {p.status} payment cannot become {to}", "bad_transition", p.id)
    previous, p.status = p.status, to
    amount = f"₹{to_rupees(p.amount_paise):,.2f}"
    label = METHOD_LABEL[p.method]
    log.info("payment %s order %s %s -> %s (%s)", p.id, order.id, previous, to, p.method)  # ids only, never customer data
    if to in TERMINAL:
        p.next_action = None
    if to == "pending":
        if order.payment_status != "paid":
            order.payment_status = "processing"
        if previous == "created":
            add_event(db, order, "payment_started", f"{label} payment of {amount} started (attempt {p.attempt_no}).", "customer")
    elif to == "succeeded":
        p.paid_at, p.failure_code, p.failure_message = datetime.now(timezone.utc), None, None
        if order.payment_status == "paid":
            p.details = {**(p.details or {}), "duplicate_charge": True}
            add_event(db, order, "payment_duplicate", f"A second payment of {amount} ({_describe(p)}) was received for an already-paid order and needs a refund. Receipt {p.receipt}.", "system")
        else:
            order.payment_status = "paid"
            late = " It arrived after the attempt timed out and was matched to this order." if previous in ("expired", "cancelled") else ""
            add_event(db, order, "payment_paid", f"{amount} received via {label} ({_describe(p)}). Receipt {p.receipt}.{late}", "system")
    elif to in ("failed", "expired"):
        if order.payment_status != "paid":
            order.payment_status = "failed"
        add_event(db, order, "payment_failed" if to == "failed" else "payment_expired", f"{label} payment {to}: {p.failure_message or note or 'no money was taken'}", "system")
    elif to == "cancelled":
        if order.payment_status != "paid" and not _other_active(db, order, p):
            order.payment_status = "pending"
        add_event(db, order, "payment_cancelled", f"{label} payment was cancelled before completion. No money was taken.", "customer")


def _other_active(db: Session, order: Order, p: Payment) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Payment).where(Payment.order_id == order.id, Payment.id != p.id, Payment.status.in_(ACTIVE))))


def _expire_if_due(db: Session, order: Order, p: Payment) -> None:
    if p.status in ACTIVE and datetime.now(timezone.utc) >= aware(p.expires_at):
        try:
            get_gateway().cancel(p)
        except GatewayError:
            pass
        p.failure_code, p.failure_message = "expired", "The payment window expired and no money was taken. Please start the payment again."
        _transition(db, order, p, "expired")


# ---------------------------------------------------------------- operations

def create_payment(db: Session, order: Order, req: dict, idempotency_key: str | None) -> Payment:
    if idempotency_key:
        existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
        if existing:
            if existing.order_id != order.id:
                raise PaymentError("That idempotency key was already used for a different order.", "idempotency_conflict")
            return existing
    if order.status == "cancelled":
        raise PaymentError("This order was cancelled.", "cancelled")
    if order.payment_status == "paid":
        raise PaymentError("This order is already paid.", "already_paid")
    method = req.get("method")
    if method not in METHODS:
        raise PaymentError("Choose UPI, card or net banking.", "invalid_method")

    for old in list_payments(db, order):  # settle stale attempts first so they don't block a retry
        if old.status in ACTIVE:
            refresh(db, old, commit=False)
    live = next((x for x in list_payments(db, order) if x.status in ACTIVE), None)
    if live:
        raise PaymentError("A payment for this order is already in progress. Finish it, or cancel it to start another.", "payment_in_progress", live.id)

    quote = db.get(Quote, order.quote_id)
    s = get_settings()
    n = (db.scalar(select(func.count()).select_from(Payment).where(Payment.order_id == order.id)) or 0) + 1
    p = Payment(order_id=order.id, method=method, amount_paise=to_paise(quote.totals["first_payment"]), currency="INR", status="created",
                gateway=get_gateway().name, idempotency_key=idempotency_key, receipt=f"{order.id}/{n}", attempt_no=n, details={}, gateway_data={},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=s.payment_expiry_minutes))
    db.add(p)
    db.flush()
    try:
        result = get_gateway().create(p, req)
    except GatewayError as e:
        db.rollback()  # nothing was created at the gateway, nothing is kept here
        raise PaymentError(str(e), e.code) from e
    _apply(db, order, p, result)
    try:
        db.commit()
    except IntegrityError:  # two requests raced on the same idempotency key
        db.rollback()
        again = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key)) if idempotency_key else None
        if again:
            return again
        raise
    return p


def refresh(db: Session, p: Payment, commit: bool = True) -> Payment:
    """Reconcile an in-flight payment with the gateway (so a lost webhook never strands a customer), then apply expiry."""
    if p.status in ACTIVE:
        order = db.get(Order, p.order_id)
        try:
            result = get_gateway().refresh(p)
        except GatewayError as e:
            log.warning("payment %s refresh failed: %s", p.id, e.code)
            result = None
        if result:
            _apply(db, order, p, result)
        _expire_if_due(db, order, p)
        if commit:
            db.commit()
    return p


def cancel(db: Session, p: Payment) -> Payment:
    refresh(db, p, commit=False)
    if p.status not in ACTIVE:
        db.commit()
        raise PaymentError(f"This payment is already {p.status} and cannot be cancelled.", "not_cancellable", p.id)
    try:
        get_gateway().cancel(p)
    except GatewayError:
        pass
    _transition(db, db.get(Order, p.order_id), p, "cancelled")
    db.commit()
    return p


def _require_pending(db: Session, p: Payment) -> Order:
    refresh(db, p, commit=True)
    if p.status != "pending":
        raise PaymentError(f"This payment is {p.status}." + (" Please start again." if p.status in ("failed", "expired", "cancelled") else ""), "not_pending", p.id)
    return db.get(Order, p.order_id)


def submit_otp(db: Session, p: Payment, otp: str) -> Payment:
    order = _require_pending(db, p)
    try:
        result = get_gateway().submit_otp(p, otp)
    except _WrongOtp as e:
        p.gateway_data = e.new_private
        db.commit()
        raise PaymentError(str(e), "otp_incorrect", p.id) from e
    except GatewayError as e:
        raise PaymentError(str(e), e.code, p.id) from e
    _apply(db, order, p, result)
    db.commit()
    return p


def confirm(db: Session, p: Payment, data: dict) -> Payment:
    refresh(db, p, commit=True)
    if p.status == "succeeded":
        return p  # the webhook / a poll got there first: the customer has paid, so the browser's confirm call is a harmless no-op, never an error
    order = _require_pending(db, p)
    try:
        result = get_gateway().confirm(p, data)
    except GatewayError as e:
        raise PaymentError(str(e), e.code, p.id) from e
    _apply(db, order, p, result)
    db.commit()
    return p


def sandbox_bank_action(db: Session, ref: str, outcome: str) -> Payment:
    gw = get_gateway()
    if not isinstance(gw, SandboxGateway):
        raise PaymentError("Not found", "not_found")
    p = db.scalar(select(Payment).where(Payment.gateway_ref == ref))
    if not p:
        raise PaymentError("Not found", "not_found")
    order = _require_pending(db, p)
    try:
        result = gw.bank_action(p, outcome)
    except GatewayError as e:
        raise PaymentError(str(e), e.code, p.id) from e
    _apply(db, order, p, result)
    db.commit()
    return p


# ---------------------------------------------------------------- webhooks

def handle_webhook(db: Session, gateway_name: str, headers: dict, raw_body: bytes) -> dict:
    gw = get_gateway()
    if gateway_name != gw.name:
        raise PaymentError("Unknown gateway", "not_found")
    if not gw.verify_webhook(headers, raw_body):
        raise PaymentError("Invalid signature", "webhook_bad_signature")
    try:
        data = json.loads(raw_body)
    except ValueError as e:
        raise PaymentError("Malformed body", "bad_body") from e
    event = gw.parse_webhook(headers, data)
    if not event:
        return {"status": "ignored"}  # an event type we don't act on: acknowledge so the gateway stops retrying

    row = PaymentWebhookEvent(gateway=gw.name, event_id=event.event_id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate"}  # already processed this delivery

    p = db.scalar(select(Payment).where(Payment.gateway_ref == event.gateway_ref)) if event.gateway_ref else None
    if not p:
        row.outcome = "unknown_payment"
        db.commit()
        log.warning("webhook %s for unknown payment ref", event.event_id)
        return {"status": "ignored"}
    order = db.get(Order, p.order_id)
    if event.amount_paise is not None and event.amount_paise != p.amount_paise:
        row.outcome = "amount_mismatch"
        add_event(db, order, "payment_alert", "A payment notification with a different amount than the order total was rejected for review.", "system")
        db.commit()
        log.error("webhook amount mismatch on payment %s", p.id)
        return {"status": "rejected", "reason": "amount_mismatch"}

    if event.status == "succeeded":
        if event.gateway_payment_id:
            p.gateway_payment_id = event.gateway_payment_id
        try:
            _transition(db, order, p, "succeeded")
            row.outcome = "succeeded"
        except PaymentError:  # e.g. we already recorded this attempt as failed: keep it for a human to reconcile, don't error the webhook
            row.outcome = f"conflict_{p.status}"
            add_event(db, order, "payment_alert", f"The gateway reports a success for a payment we recorded as {p.status}. Please reconcile manually (receipt {p.receipt}).", "system")
    elif event.status == "failed" and p.status in ACTIVE:
        p.failure_code, p.failure_message = event.failure_code, event.failure_message or "The payment failed."
        _transition(db, order, p, "failed")
        row.outcome = "failed"
    elif event.status == "attempt_failed" and p.status in ACTIVE:
        p.details = {**(p.details or {}), "last_failure": event.failure_message or "An attempt failed; you can retry."}
        row.outcome = "attempt_failed"
    else:
        row.outcome = f"no_change_{p.status}"
    db.commit()
    return {"status": "ok", "outcome": row.outcome}
