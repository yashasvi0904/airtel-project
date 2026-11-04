"""Back-office: lead overview, segmentation, orders, KYC queue and conversion metrics."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Journey, KycCase, Order, User
from ..schemas import AdvanceIn, DecisionIn
from ..security import admin_user
from ..services import analytics
from ..services import orders as svc
from ..services.kyc import service as kyc
from ..services.profile import build_profile

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_user)])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    orders = db.scalars(select(Order)).all()
    by_status, by_kyc = {}, {}
    for o in orders:
        by_status[o.status] = by_status.get(o.status, 0) + 1
        by_kyc[o.kyc_status] = by_kyc.get(o.kyc_status, 0) + 1
    paid = [o for o in orders if o.payment_status == "paid"]
    journeys = db.scalar(select(func.count(Journey.id))) or 0
    quoted = db.scalar(select(func.count(Journey.id)).where(Journey.stage.in_(["quoted", "ordered"]))) or 0
    return {
        "historical": analytics.kpis(),
        "live": {
            "journeys": journeys, "quoted": quoted, "orders": len(orders), "paid_orders": len(paid),
            "activated": by_status.get("activated", 0),
            "journey_to_order_pct": round(100 * len(orders) / journeys, 1) if journeys else 0,
            "monthly_value_booked": round(sum(o.monthly_total for o in paid), 2),
            "setup_value_booked": round(sum(o.setup_total for o in paid), 2),
            "orders_by_status": by_status, "orders_by_kyc": by_kyc,
        },
    }


@router.get("/funnel")
def funnel():
    return {"funnel": analytics.funnel(), "drop_reasons": analytics.drop_reasons(), "weekly": analytics.weekly_trend()}


@router.get("/segments")
def segments():
    return {"segments": analytics.segments(), "products": analytics.product_attach()}


@router.get("/breakdown/{by}")
def breakdown(by: str):
    try:
        return {"by": by, "rows": analytics.breakdown(by)}
    except ValueError:
        raise HTTPException(404, "Unknown breakdown")


@router.get("/leads")
def leads(page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100), segment: str | None = None, source: str | None = None,
          stage: str | None = None, q: str | None = Query(None, max_length=80), sort: str = "propensity", open_only: bool = False):
    return analytics.leads_page(page, size, segment, source, stage, q, sort, open_only)


@router.get("/propensity")
def propensity():
    m = analytics.propensity_model()
    return {"auc_holdout": m["auc"], "top_drivers": m["top_drivers"], "note": "Logistic regression on lead profile only (no funnel-stage leakage)."}


@router.get("/orders")
def orders(db: Session = Depends(get_db), status: str | None = None):
    stmt = select(Order).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    return [{**svc.order_dict(o), "customer": (db.get(User, o.user_id).email if db.get(User, o.user_id) else None)} for o in db.scalars(stmt)]


@router.post("/orders/{order_id}/advance")
def advance(order_id: str, body: AdvanceIn, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    try:
        svc.advance(db, o, body.to, body.note)
    except svc.OrderError as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)}) from e
    return svc.order_dict(o)


@router.get("/kyc")
def kyc_queue(db: Session = Depends(get_db)):
    out = []
    for case in db.scalars(select(KycCase).order_by(KycCase.updated_at.desc())):
        o = db.get(Order, case.order_id)
        res = case.result or {}
        out.append({"order_id": case.order_id, "business_name": o.business_name if o else "", "status": case.status,
                    "summary": res.get("summary"), "issues": res.get("issues", []), "updated_at": case.updated_at.isoformat(),
                    "document_status": res.get("document_status", {})})
    return out


@router.post("/kyc/{order_id}/decision")
def kyc_decision(order_id: str, body: DecisionIn, db: Session = Depends(get_db)):
    """Manual review of 'needs_review' cases (human-in-the-loop)."""
    o = db.get(Order, order_id)
    case = db.scalar(select(KycCase).where(KycCase.order_id == order_id))
    if not o or not case:
        raise HTTPException(404, "KYC case not found")
    if case.status != "needs_review":
        raise HTTPException(409, "Only cases waiting for review can be decided manually")
    if body.approve:
        case.status = "approved"
        svc.mark_kyc(db, o, "approved", body.note or "Approved after manual review.", "admin")
    else:
        case.status = "action_required"
        svc.mark_kyc(db, o, "action_required", body.note or "Manual review found a problem; documents must be corrected.", "admin")
        svc.add_event(db, o, "kyc_action_required", body.note or "Manual review found a problem.", "admin")
    db.commit()
    return {"order_id": order_id, "kyc_status": o.kyc_status}


@router.get("/advisor-leads")
def advisor_leads(db: Session = Depends(get_db)):
    """Stretch goal: journeys the advisor could not close - who to call, ranked by propensity."""
    out = []
    ordered = set(db.scalars(select(Order.journey_id)))
    for j in db.scalars(select(Journey).order_by(Journey.updated_at.desc())):
        if j.id in ordered:
            continue
        prof = build_profile({**j.profile, "language": j.language})
        out.append({"journey_id": j.id, "business_name": prof.business_name, "city": prof.city, "segment": prof.segment, "stage": j.stage,
                    "employees": prof.employees, "sites": prof.sites, "phone": prof.phone or None,
                    "propensity": analytics.propensity_for_profile(j.profile, prof.segment, prof.city_tier),
                    "needs": {k: v for k, v in (j.needs or {}).items() if k not in ("asked", "last_question")},
                    "updated_at": j.updated_at.isoformat()})
    return sorted(out, key=lambda r: -r["propensity"])


@router.post("/maintenance/purge-documents")
def purge(db: Session = Depends(get_db)):
    return {"purged": kyc.purge_expired(db)}
