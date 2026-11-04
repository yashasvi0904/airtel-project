"""Order lifecycle: creation, simulated payment, KYC gating, install scheduling and activation."""
import secrets
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Journey, KycCase, Order, OrderEvent, Quote, User

ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
STATUSES = ["placed", "kyc_verified", "install_scheduled", "installing", "activated", "cancelled"]
# admin-driven transitions (customer scheduling and KYC outcomes move the other states)
ADMIN_TRANSITIONS = {
    "install_scheduled": ["installing"],
    "installing": ["activated"],
    "kyc_verified": [],
    "placed": [],
}
SLOT_WINDOWS = {"morning": "9:00 - 13:00", "afternoon": "14:00 - 18:00"}


class OrderError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _new_id(db: Session) -> str:
    today = get_settings().today.strftime("%Y%m%d")
    while True:
        oid = f"UD-{today}-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(6))
        if not db.get(Order, oid):
            return oid


def add_event(db: Session, order: Order, status: str, note: str = "", actor: str = "system"):
    db.add(OrderEvent(order_id=order.id, status=status, note=note, actor=actor))


def create_order(db: Session, user: User, journey: Journey, quote: Quote) -> Order:
    if quote.journey_id != journey.id:
        raise OrderError("Quote does not belong to this journey", "mismatch")
    existing = db.scalar(select(Order).where(Order.quote_id == quote.id))
    if existing:
        return existing
    t = quote.totals
    order = Order(
        id=_new_id(db), user_id=user.id, journey_id=journey.id, quote_id=quote.id,
        business_name=(journey.profile or {}).get("business_name", "Your business"),
        segment=(journey.needs or {}).get("segment", "") or (journey.profile or {}).get("segment", ""),
        term_months=quote.term_months, monthly_total=t["monthly_total"], setup_total=t["setup_total"],
        install_days=t.get("install_days", 0), status="placed", kyc_status="not_started", payment_status="pending",
    )
    db.add(order)
    journey.user_id = user.id
    journey.stage = "ordered"
    db.flush()
    add_event(db, order, "placed", f"Order placed for {len(quote.items)} product(s).", "customer")
    db.commit()
    return order


def pay(db: Session, order: Order, method: str, simulate: str = "success") -> Order:
    """Simulated payment (no gateway is integrated). 'fail' reproduces the 'first payment failed' drop reason."""
    if order.payment_status == "paid":
        raise OrderError("This order is already paid", "already_paid")
    if order.status == "cancelled":
        raise OrderError("This order was cancelled", "cancelled")
    if simulate == "fail":
        order.payment_status = "failed"
        add_event(db, order, "payment_failed", f"Simulated {method.upper()} payment failed. Please retry.", "system")
    else:
        order.payment_status = "paid"
        add_event(db, order, "payment_paid", f"Simulated {method.upper()} payment of Rs {order.monthly_total + order.setup_total:,.2f} received (demo - no real charge).", "system")
    db.commit()
    return order


def available_slots(order: Order, days: int = 10) -> list[dict]:
    """Visit dates start once the longest-lead product can be ready (typical_install_days), skipping Sundays."""
    today = get_settings().today
    earliest = today + timedelta(days=max(1, order.install_days - 1))
    out, d = [], earliest
    while len(out) < days:
        if d.weekday() != 6:
            out.append({"date": d.isoformat(), "weekday": d.strftime("%A"), "windows": [{"id": k, "label": v} for k, v in SLOT_WINDOWS.items()]})
        d += timedelta(days=1)
    return out


def schedule(db: Session, order: Order, day: str, window: str) -> Order:
    if order.payment_status != "paid":
        raise OrderError("Complete the payment before scheduling installation", "payment_required")
    if order.kyc_status not in ("verified", "approved"):
        raise OrderError("KYC must be verified before installation can be scheduled", "kyc_required")
    if order.status not in ("kyc_verified", "install_scheduled"):
        raise OrderError(f"Installation cannot be scheduled while the order is '{order.status}'", "bad_state")
    if day not in {s["date"] for s in available_slots(order)}:
        raise OrderError("That date is not available. Pick one of the offered slots.", "bad_slot")
    d = date.fromisoformat(day)
    order.install_slot_date, order.install_slot_window = day, window
    order.expected_activation = (d + timedelta(days=1)).isoformat()
    order.status = "install_scheduled"
    add_event(db, order, "install_scheduled", f"Technician visit booked for {day}, {SLOT_WINDOWS[window]}.", "customer")
    db.commit()
    return order


def mark_kyc(db: Session, order: Order, status: str, note: str = "", actor: str = "system"):
    order.kyc_status = status
    if status in ("verified", "approved") and order.status == "placed":
        order.status = "kyc_verified"
        add_event(db, order, "kyc_verified", note or "KYC verified.", actor)


def advance(db: Session, order: Order, to: str, note: str = "", actor: str = "admin") -> Order:
    if to not in ADMIN_TRANSITIONS.get(order.status, []) and to != "cancelled":
        raise OrderError(f"Cannot move an order from '{order.status}' to '{to}'", "bad_transition")
    if to == "cancelled" and order.status == "activated":
        raise OrderError("An activated order cannot be cancelled", "bad_transition")
    order.status = to
    if to == "activated":
        order.activated_on = get_settings().today.isoformat()
    add_event(db, order, to, note or {"installing": "Technician has started installation.", "activated": "Services are live.", "cancelled": "Order cancelled."}.get(to, ""), actor)
    db.commit()
    return order


def tracker(order: Order, kyc: KycCase | None) -> dict:
    """Customer-facing timeline: what is done, what is next, and what the customer must do."""
    kyc_status = order.kyc_status
    paid = order.payment_status == "paid"
    kyc_ok = kyc_status in ("verified", "approved")
    sched = order.status in ("install_scheduled", "installing", "activated")
    steps = [
        {"key": "placed", "label": "Order placed", "state": "done"},
        {"key": "payment", "label": "Payment", "state": "done" if paid else ("failed" if order.payment_status == "failed" else "current")},
        {"key": "kyc", "label": "KYC verification",
         "state": "done" if kyc_ok else ("review" if kyc_status == "needs_review" else ("blocked" if kyc_status in ("rejected", "action_required", "incomplete") else "current"))},
        {"key": "install_scheduled", "label": "Installation scheduled", "state": "done" if sched else ("current" if paid and kyc_ok else "pending")},
        {"key": "installing", "label": "Installation in progress", "state": "done" if order.status in ("installing", "activated") else ("current" if order.status == "install_scheduled" else "pending")},
        {"key": "activated", "label": "Activated", "state": "done" if order.status == "activated" else "pending"},
    ]
    if order.status == "cancelled":
        for s in steps:
            if s["state"] != "done":
                s["state"] = "cancelled"
    next_action = None
    if order.status == "cancelled":
        next_action = None
    elif not paid:
        next_action = {"type": "pay", "message": "Complete your payment to continue."}
    elif kyc_status in ("not_started", "awaiting_documents"):
        next_action = {"type": "kyc", "message": "Give consent and upload your KYC documents."}
    elif kyc_status in ("action_required", "incomplete", "rejected"):
        next_action = {"type": "kyc_fix", "message": "Some KYC documents need your attention."}
    elif kyc_status == "needs_review":
        next_action = {"type": "wait", "message": "Our team is reviewing a few details in your documents (usually within 1 working day)."}
    elif order.status == "kyc_verified":
        next_action = {"type": "schedule", "message": "Pick a convenient installation slot."}
    elif order.status == "install_scheduled":
        next_action = {"type": "wait", "message": f"Technician visit on {order.install_slot_date}."}
    elif order.status == "installing":
        next_action = {"type": "wait", "message": "Installation is in progress."}
    return {"steps": steps, "next_action": next_action}


def order_dict(order: Order, kyc: KycCase | None = None) -> dict:
    return {
        "id": order.id, "status": order.status, "kyc_status": order.kyc_status, "payment_status": order.payment_status,
        "business_name": order.business_name, "term_months": order.term_months,
        "monthly_total": order.monthly_total, "setup_total": order.setup_total,
        "install_slot": {"date": order.install_slot_date, "window": order.install_slot_window,
                         "window_label": SLOT_WINDOWS.get(order.install_slot_window or "")} if order.install_slot_date else None,
        "expected_activation": order.expected_activation, "activated_on": order.activated_on,
        "typical_install_days": order.install_days,
        "created_at": order.created_at.isoformat(), "updated_at": order.updated_at.isoformat(),
        "events": [{"status": e.status, "note": e.note, "actor": e.actor, "at": e.created_at.isoformat()} for e in order.events],
        "tracker": tracker(order, kyc),
    }
