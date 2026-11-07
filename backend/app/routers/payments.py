"""Payment endpoints: methods, start an attempt (UPI / net banking / card), poll, OTP, cancel, gateway webhook.

Customer endpoints are owner-scoped (404, not 403, for other users' orders). The amount is never accepted from the
client. Card data is accepted only for the sandbox gateway and is dropped as soon as the gateway call returns.
"""
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Order, Payment, User
from ..security import current_user, payment_limiter
from ..services.payments import service as svc
from .orders import own_order

router = APIRouter(prefix="/api")

CONFLICT_CODES = {"payment_in_progress", "already_paid", "cancelled", "not_pending", "not_cancellable", "bad_transition", "idempotency_conflict", "bad_state"}
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,80}$")


class UpiIn(BaseModel):
    flow: Literal["collect", "intent"] = "collect"
    vpa: str | None = Field(default=None, max_length=80)


class NetBankingIn(BaseModel):
    bank: str = Field(max_length=12)


class CardIn(BaseModel):
    number: str = Field(max_length=32, repr=False)
    name: str = Field(default="", max_length=80)
    exp_month: int = Field(ge=0, le=99)
    exp_year: int = Field(ge=0, le=9999)
    cvv: str = Field(max_length=4, repr=False)


class PaymentIn(BaseModel):
    method: Literal["upi", "netbanking", "card"]
    upi: UpiIn | None = None
    netbanking: NetBankingIn | None = None
    card: CardIn | None = None


class OtpIn(BaseModel):
    otp: str = Field(min_length=4, max_length=8, repr=False)


class BankIn(BaseModel):
    outcome: Literal["authorize", "decline", "abandon"]


def _http(e: svc.PaymentError) -> HTTPException:
    if e.code == "webhook_bad_signature":
        return HTTPException(401, "Invalid signature")
    if e.code == "not_found":
        return HTTPException(404, "Not found")
    if e.code in CONFLICT_CODES:
        return HTTPException(409, {"code": e.code, "message": str(e), "payment_id": e.payment_id})
    if e.code == "gateway_unreachable":
        return HTTPException(424, {"code": e.code, "message": str(e)})  # not 502/503: the UI treats those as 'server asleep'
    return HTTPException(422, str(e))


def own_payment(payment_id: str, db: Session, user: User) -> Payment:
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(404, "Payment not found")
    own_order(p.order_id, db, user)
    return p


@router.get("/payments/methods")
def payment_methods():
    return svc.methods_view()


@router.post("/orders/{order_id}/payments", status_code=201, dependencies=[Depends(payment_limiter)])
def start_payment(order_id: str, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(current_user),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    o = own_order(order_id, db, user)
    if idempotency_key and not KEY_RE.match(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 8-80 letters, digits, '-' or '_'")
    req = body.model_dump()
    if req.get("card") and req["card"]["exp_year"] < 100:
        req["card"]["exp_year"] += 2000  # 2-digit year -> 4-digit
    try:
        return svc.payment_view(svc.create_payment(db, o, req, idempotency_key))
    except svc.PaymentError as e:
        raise _http(e) from e


@router.get("/orders/{order_id}/payments")
def order_payments(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    out = []
    for p in svc.list_payments(db, o):
        svc.refresh(db, p)  # settles expiry / reconciles with the gateway so the page never shows a stale 'pending'
        out.append(svc.payment_view(p))
    return {"payments": out, "order_payment_status": db.get(Order, o.id).payment_status}


@router.get("/payments/{payment_id}")
def get_payment(payment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = own_payment(payment_id, db, user)
    svc.refresh(db, p)
    return {**svc.payment_view(p), "order_payment_status": db.get(Order, p.order_id).payment_status}


@router.post("/payments/{payment_id}/cancel")
def cancel_payment(payment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = own_payment(payment_id, db, user)
    try:
        return svc.payment_view(svc.cancel(db, p))
    except svc.PaymentError as e:
        raise _http(e) from e


@router.post("/payments/{payment_id}/otp", dependencies=[Depends(payment_limiter)])
def payment_otp(payment_id: str, body: OtpIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = own_payment(payment_id, db, user)
    try:
        return svc.payment_view(svc.submit_otp(db, p, body.otp))
    except svc.PaymentError as e:
        raise _http(e) from e


@router.post("/payments/{payment_id}/confirm", dependencies=[Depends(payment_limiter)])
def payment_confirm(payment_id: str, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Hosted-checkout gateways (Razorpay): the browser reports the gateway's ids + signature; the server verifies them."""
    p = own_payment(payment_id, db, user)
    try:
        return svc.payment_view(svc.confirm(db, p, {k: str(v) for k, v in body.items() if isinstance(v, (str, int))}))
    except svc.PaymentError as e:
        raise _http(e) from e


@router.post("/payments/sandbox/{ref}/bank", dependencies=[Depends(payment_limiter)])
def sandbox_bank(ref: str, body: BankIn, db: Session = Depends(get_db)):
    """The sandbox 'bank page'. Unauthenticated on purpose (a real bank page is a third party); only exists for the sandbox gateway."""
    try:
        p = svc.sandbox_bank_action(db, ref, body.outcome)
    except svc.PaymentError as e:
        raise _http(e) from e
    return {"payment_id": p.id, "order_id": p.order_id, "status": p.status}


@router.post("/payments/webhook/{gateway}")
async def payment_webhook(gateway: str, request: Request, db: Session = Depends(get_db)):
    raw = await request.body()  # the signature is over the exact bytes received, so do not re-serialise
    try:
        return svc.handle_webhook(db, gateway, {k.lower(): v for k, v in request.headers.items()}, raw)
    except svc.PaymentError as e:
        raise _http(e) from e
