"""Business onboarding, AI advisor, recommendations and quotes. Journeys are guest-accessible by unguessable id."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Journey, Quote, User
from ..schemas import MessageIn, ProfileIn, QuotePreviewIn, SelectionIn
from ..security import current_user_optional
from ..services import analytics
from ..services.advisor import engine as advisor
from ..services.advisor.providers import get_provider
from ..services.catalogue import all_products
from ..services.eligibility import check_eligibility, validate_selection
from ..services.pricing import build_quote
from ..services.profile import build_profile
from ..services.recommender import build_bundles, explorer, suggest_fixes

router = APIRouter(prefix="/api")


def get_journey(journey_id: str, db: Session, user: User | None) -> Journey:
    j = db.get(Journey, journey_id)
    if not j:
        raise HTTPException(404, "Journey not found")
    if j.user_id and (user is None or (user.id != j.user_id and user.role != "admin")):
        raise HTTPException(403, "This journey belongs to another account")
    return j


def profile_view(j: Journey) -> dict:
    p = build_profile({**j.profile, "language": j.language})
    return {**j.profile, "segment": p.segment, "city_tier": p.city_tier, "state": p.state, "gstin_status": p.gstin_status,
            "gstin_masked": (p.gstin[:2] + "*" * 10 + p.gstin[-3:]) if p.gstin else None}


def journey_dict(j: Journey) -> dict:
    prof = profile_view(j)
    prof.pop("gstin", None)
    return {"id": j.id, "stage": j.stage, "language": j.language, "profile": prof, "needs": {k: v for k, v in (j.needs or {}).items() if k not in ("asked", "last_question")},
            "selection": j.selection or None, "user_id": j.user_id}


@router.post("/journeys", status_code=201)
def create_journey(body: ProfileIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    data = body.model_dump()
    prof = build_profile(data)
    from ..services.profile import city_info

    if not city_info(prof.city):
        raise HTTPException(422, "Please choose your city from the list - Accel Business currently serves tier 1 and tier 2 cities.")
    if data.get("gstin") and prof.gstin_status in ("invalid", "not_found"):
        raise HTTPException(422, "That GSTIN could not be validated. Check the number or leave it blank and add it later.")
    j = Journey(language=body.language, profile={**data, "segment": prof.segment}, user_id=None, stage="onboarding")
    if user:
        j.user_id = user.id
    db.add(j)
    db.commit()
    score = analytics.propensity_for_profile(data, prof.segment, prof.city_tier)
    return {**journey_dict(j), "propensity": score}


@router.get("/journeys/{journey_id}")
def read_journey(journey_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    return journey_dict(get_journey(journey_id, db, user))


@router.patch("/journeys/{journey_id}/profile")
def update_profile(journey_id: str, body: dict, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    """Partial update (e.g. add a GSTIN after seeing which products need it)."""
    j = get_journey(journey_id, db, user)
    allowed = {"gstin", "has_gstin", "has_udyam", "monthly_budget", "employees", "sites", "current_internet", "monthly_telecom_spend", "contact_name", "phone"}
    merged = {**j.profile, **{k: v for k, v in body.items() if k in allowed}}
    try:
        validated = ProfileIn(**{k: merged.get(k) for k in ProfileIn.model_fields if k in merged}).model_dump()
    except Exception as e:
        raise HTTPException(422, str(e)) from e
    prof = build_profile({**validated, "language": j.language})
    if validated.get("gstin") and prof.gstin_status in ("invalid", "not_found"):
        raise HTTPException(422, "That GSTIN could not be validated against the registry.")
    if validated.get("gstin"):
        validated["has_gstin"] = True
    j.profile = {**validated, "segment": prof.segment}
    j.selection = {}  # eligibility may have changed
    db.commit()
    return journey_dict(j)


# ---------------------------------------------------------------- advisor

@router.get("/journeys/{journey_id}/advisor")
def advisor_history(journey_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    return {"messages": [{"role": m.role, "content": m.content, "at": m.created_at.isoformat()} for m in j.messages],
            "provider": get_provider().name, "stage": j.stage}


@router.post("/journeys/{journey_id}/advisor/start")
def advisor_start(journey_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    if j.messages:
        return {"messages": [{"role": m.role, "content": m.content} for m in j.messages], "provider": get_provider().name, "resumed": True}
    out = advisor.start(db, j)
    return {"messages": [{"role": "assistant", "content": out["reply"]}], **out, "resumed": False}


@router.post("/journeys/{journey_id}/advisor/message")
def advisor_message(journey_id: str, body: MessageIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    if not j.messages:
        advisor.start(db, j)
        db.refresh(j)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Message is empty")
    return advisor.turn(db, j, text, all_products(db))


# ---------------------------------------------------------------- recommendations / selection / quotes

@router.get("/journeys/{journey_id}/recommendations")
def recommendations(journey_id: str, term_months: int | None = None, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    cat = all_products(db)
    prof = build_profile({**j.profile, "language": j.language})
    rec = build_bundles(prof, j.needs or {}, cat, term_months)
    names = {pid: p.product_name for pid, p in cat.items()}
    for t in rec["tiers"].values():
        for it in t["items"]:
            it["name"] = names[it["product_id"]]
            it["unit"] = cat[it["product_id"]].unit
            it["category"] = cat[it["product_id"]].category
    rec.pop("attach_rates", None)
    return {"journey": journey_dict(j), "recommendation": rec, "catalogue": explorer(prof, cat)}


def _preview(journey: Journey, items: list[dict], term: int, db: Session) -> dict:
    cat = all_products(db)
    prof = build_profile({**journey.profile, "language": journey.language})
    errors = validate_selection(items, term, prof, cat)
    out = {"valid": not errors, "errors": errors, "fixes": suggest_fixes(errors, items, prof, cat), "quote": None}
    if not errors:
        out["quote"] = build_quote(items, term, cat, prof.monthly_telecom_spend)
    else:
        known = [i for i in items if i["product_id"] in cat]
        if known:
            out["indicative_quote"] = build_quote(known, max(term, 1), cat, prof.monthly_telecom_spend)
    return out


@router.post("/quotes/preview")
def preview(body: QuotePreviewIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    """Dynamic recalculation: stateless; the page calls this on every toggle/quantity/term change."""
    j = get_journey(body.journey_id, db, user)
    return _preview(j, [i.model_dump() for i in body.items], body.term_months, db)


@router.put("/journeys/{journey_id}/selection")
def save_selection(journey_id: str, body: SelectionIn, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    items = [i.model_dump() for i in body.items]
    res = _preview(j, items, body.term_months, db)
    if res["valid"]:
        j.selection = {"items": items, "term_months": body.term_months}
        j.stage = "selected"
        db.commit()
    return res


@router.post("/journeys/{journey_id}/quote", status_code=201)
def create_quote(journey_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    j = get_journey(journey_id, db, user)
    sel = j.selection or {}
    if not sel.get("items"):
        raise HTTPException(409, "Choose your products before requesting a quote")
    res = _preview(j, sel["items"], sel["term_months"], db)
    if not res["valid"]:
        raise HTTPException(422, {"message": "Your selection has problems", "errors": res["errors"]})
    q = Quote(journey_id=j.id, term_months=sel["term_months"], items=res["quote"]["items"], totals=res["quote"]["totals"])
    db.add(q)
    j.stage = "quoted"
    db.commit()
    return quote_dict(q)


def quote_dict(q: Quote) -> dict:
    return {"id": q.id, "journey_id": q.journey_id, "term_months": q.term_months, "items": q.items, "totals": q.totals,
            "created_at": q.created_at.isoformat()}


@router.get("/quotes/{quote_id}")
def read_quote(quote_id: str, db: Session = Depends(get_db), user: User | None = Depends(current_user_optional)):
    q = db.get(Quote, quote_id)
    if not q:
        raise HTTPException(404, "Quote not found")
    get_journey(q.journey_id, db, user)
    return quote_dict(q)
