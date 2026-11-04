"""Checkout, order tracking, install scheduling and Smart KYC endpoints (all owner-scoped)."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Journey, KycCase, Order, Quote, User
from ..schemas import ConsentIn, OrderIn, PayIn, ScheduleIn
from ..security import current_user, upload_limiter
from ..services import orders as svc
from ..services.kyc import service as kyc
from ..services.kyc.parsers import DOC_LABELS

router = APIRouter(prefix="/api")


def own_order(order_id: str, db: Session, user: User) -> Order:
    o = db.get(Order, order_id)
    if not o or (o.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Order not found")  # 404, not 403, so ids cannot be probed
    return o


def kyc_case(db: Session, order: Order) -> KycCase | None:
    return db.scalar(select(KycCase).where(KycCase.order_id == order.id))


def view(db: Session, order: Order) -> dict:
    return svc.order_dict(order, kyc_case(db, order))


def _wrap(fn, *a):
    try:
        return fn(*a)
    except svc.OrderError as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)}) from e


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not body.accept_terms:
        raise HTTPException(422, "Please accept the terms to place the order")
    q = db.get(Quote, body.quote_id)
    if not q:
        raise HTTPException(404, "Quote not found")
    j = db.get(Journey, q.journey_id)
    if j.user_id and j.user_id != user.id and user.role != "admin":
        raise HTTPException(403, "This quote belongs to another account")
    order = _wrap(svc.create_order, db, user, j, q)
    return view(db, order)


@router.get("/orders")
def my_orders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())).all()
    return [view(db, o) for o in rows]


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    quote = db.get(Quote, o.quote_id)
    return {**view(db, o), "items": quote.items, "totals": quote.totals}


@router.post("/orders/{order_id}/pay")
def pay(order_id: str, body: PayIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    return view(db, _wrap(svc.pay, db, o, body.method, body.simulate))


@router.get("/orders/{order_id}/slots")
def slots(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"slots": svc.available_slots(own_order(order_id, db, user))}


@router.post("/orders/{order_id}/schedule")
def schedule(order_id: str, body: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    return view(db, _wrap(svc.schedule, db, o, body.date, body.window))


# ---------------------------------------------------------------- Smart KYC

@router.get("/orders/{order_id}/kyc")
def get_kyc(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    case = kyc.get_or_create_case(db, o)
    return {**kyc.public_case(case, db), "notice": {"version": kyc.NOTICE_VERSION, "purposes": kyc.CONSENT_PURPOSES,
                                                      "retention_days": get_settings().document_retention_days},
            "doc_labels": DOC_LABELS}


@router.post("/orders/{order_id}/kyc/consent")
def consent(order_id: str, body: ConsentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    if not body.accepted:
        raise HTTPException(422, "Consent is required to verify your documents. You can also choose to verify with our field team instead.")
    if body.gstin:
        from ..services.kyc.validators import gstin_format_ok

        if not gstin_format_ok(body.gstin.upper()):
            raise HTTPException(422, "The GSTIN you entered is not a valid format")
    if body.udyam_number:
        from ..services.kyc.validators import is_valid_udyam

        if not is_valid_udyam(body.udyam_number):
            raise HTTPException(422, "The Udyam number you entered is not a valid format (UDYAM-XX-00-0000000)")
    case = kyc.get_or_create_case(db, o)
    kyc.record_consent(db, case, o, {"has_gstin": body.has_gstin, "has_udyam": body.has_udyam, "gstin": (body.gstin or "").upper(),
                                      "udyam_number": body.udyam_number or "", "signatory_name": body.signatory_name or ""})
    return kyc.public_case(case, db)


@router.post("/orders/{order_id}/kyc/documents", dependencies=[Depends(upload_limiter)])
async def upload(order_id: str, doc_type: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    case = kyc.get_or_create_case(db, o)
    data = await file.read(kyc.MAX_UPLOAD_BYTES + 1)
    try:
        kyc.save_document(db, case, doc_type, file.filename or "upload", data)
    except kyc.UploadError as e:
        raise HTTPException(422, str(e)) from e
    report = kyc.verify_case(db, case, o)
    return {**kyc.public_case(case, db), "result": report}


@router.post("/orders/{order_id}/kyc/verify")
def verify(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = own_order(order_id, db, user)
    case = kyc.get_or_create_case(db, o)
    if not case.consent:
        raise HTTPException(409, "Consent is required first")
    kyc.verify_case(db, case, o)
    return kyc.public_case(case, db)


@router.delete("/orders/{order_id}/kyc")
def erase(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Right to erasure / consent withdrawal: removes uploaded files and extracted data."""
    o = own_order(order_id, db, user)
    case = kyc.get_or_create_case(db, o)
    n = kyc.erase_case(db, case)
    o.kyc_status = "not_started"
    if o.status == "kyc_verified":
        o.status = "placed"
    db.commit()
    return {"erased_documents": n, "status": "erased"}
