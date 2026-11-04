"""Advisor turn orchestration: slots -> next question or recommendation -> reply text.

Flow per user message: extract slots (LLM or rules) -> update journey -> pick next question (deterministic) or
build the bundle (deterministic) -> render template -> optionally let the LLM rephrase -> validate -> persist.
"""
from sqlalchemy.orm import Session

from ...models import AdvisorMessage, Journey, Product
from ..profile import build_profile
from ..recommender import NEED_LABEL, build_bundles
from . import templates as T
from .providers import Provider, get_provider, reply_is_grounded
from .slots import merge_needs, next_question, wants_recommendation

MAX_QUESTIONS = 5


def _lang(journey: Journey) -> str:
    return "hi" if journey.language == "hi" else "en"


def _fmt(n: float) -> str:
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


def history_of(journey: Journey) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in journey.messages]


def recommendation_facts(rec: dict, catalogue: dict[str, Product]) -> dict:
    tier = rec["tiers"][rec["recommended_tier"]]
    q = tier["quote"]
    return {
        "segment": rec["segment"],
        "chosen_bundle": rec["recommended_tier"],
        "term_months": tier["term_months"],
        "items": [{"name": catalogue[i["product_id"]].product_name, "quantity": i["quantity"], "unit": catalogue[i["product_id"]].unit,
                   "reasons": i["reasons"]} for i in tier["items"]],
        "monthly_total_incl_gst": q["totals"]["monthly_total"] if q else None,
        "monthly_subtotal": q["totals"]["monthly_subtotal"] if q else None,
        "setup_total_incl_gst": q["totals"]["setup_total"] if q else None,
        "first_payment": q["totals"]["first_payment"] if q else None,
        "line_prices": [{"name": l["name"], "unit_price": l["unit_price"], "monthly": l["monthly"], "setup": l["setup"]} for l in (q["items"] if q else [])],
        "budget": rec.get("budget"),
        "over_budget": rec.get("over_budget"),
        "not_available": [{"name": e["name"], "why": [r["message"] for r in e["eligibility"]["reasons"]]} for e in rec["excluded"]],
    }


def render_recommendation(rec: dict, catalogue: dict[str, Product], lang: str, profile) -> str:
    name = rec["recommended_tier"]
    tier = rec["tiers"][name]
    q = tier["quote"]
    lines = [T.REC_HEAD[lang].format(tier=T.TIER_NAMES[lang][name])]
    for it in tier["items"]:
        p = catalogue[it["product_id"]]
        line_q = next((l for l in q["items"] if l["product_id"] == p.product_id), None)
        price = f" - ₹{_fmt(line_q['monthly'])}/mo" if line_q else ""
        lines.append(f"• {p.product_name} × {it['quantity']} ({p.unit}){price}: {it['reasons'][0]}")
    t = q["totals"]
    lines.append("")
    lines.append(T.REC_TOTAL[lang].format(monthly=_fmt(t["monthly_total"]), gst=_fmt(t["gst_rate_percent"]), setup=_fmt(t["setup_total"]),
                                          term=t["term_months"], first=_fmt(t["first_payment"])))
    if rec.get("budget"):
        key = T.BUDGET_OVER if rec["over_budget"] else T.BUDGET_OK
        lines.append(key[lang].format(budget=_fmt(rec["budget"])))
    if "vs_current_spend" in t and abs(t["vs_current_spend"]) >= 1:
        d = t["vs_current_spend"]
        word = ({"en": "more", "hi": "ज़्यादा"} if d > 0 else {"en": "less", "hi": "कम"})[lang]
        lines.append(T.SAVINGS[lang].format(cur=_fmt(t["current_monthly_spend"]), diff=_fmt(abs(d)), dir=word))
    if rec["excluded"]:
        items = "; ".join(
            f"{e['name']} ({e['eligibility']['reasons'][0]['message'].rstrip('.')}"
            + (f" - {e['eligibility']['unlock'][0]} to unlock" if e["eligibility"]["unlock"] else "") + ")"
            for e in rec["excluded"][:3] if e["eligibility"]["reasons"])
        if items:
            lines.append(T.EXCLUDED[lang].format(items=items))
    lines.append(T.NEXT_STEP[lang])
    return "\n".join(lines)


def _ack(update: dict, lang: str) -> str:
    parts = []
    if update.get("wants"):
        items = ", ".join(NEED_LABEL.get(w, w) for w in update["wants"])
        parts.append(T.ACK[lang]["wants"].format(items=items))
    if update.get("fibre_available") is False:
        parts.append(T.ACK[lang]["fibre_no"])
    if update.get("pain_downtime"):
        parts.append(T.ACK[lang]["downtime"])
    if update.get("priority") == "price":
        parts.append(T.ACK[lang]["price"])
    return " ".join(parts)


def start(db: Session, journey: Journey) -> dict:
    """First assistant message, built from the onboarding profile."""
    lang = _lang(journey)
    p = build_profile({**journey.profile, "language": journey.language})
    name = f", {p.contact_name.split()[0]}" if p.contact_name else ""
    needs = dict(journey.needs or {})
    asked = list(needs.get("asked", []))
    q = next_question(needs, bool(p.monthly_budget), asked)
    text = T.GREETING[lang].format(name=name, biz=p.business_name or p.business_type or "your business", city=p.city or "your city",
                                   emp=p.employees, sites=p.sites)
    if q:
        text += "\n\n" + T.QUESTIONS[lang][q]
        asked.append(q)
        needs.update(asked=asked, last_question=q)
        journey.needs = needs
    db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
    journey.stage = "advising"
    db.commit()
    return {"reply": text, "question": q, "chips": T.CHIPS[lang].get(q, []) if q else [], "recommendation_ready": False, "provider": get_provider().name}


def turn(db: Session, journey: Journey, user_text: str, catalogue: dict[str, Product], provider: Provider | None = None) -> dict:
    provider = provider or get_provider()
    lang = _lang(journey)
    needs = dict(journey.needs or {})
    asked = list(needs.get("asked", []))
    last_q = needs.get("last_question")
    history = history_of(journey)
    db.add(AdvisorMessage(journey_id=journey.id, role="user", content=user_text))

    update = provider.extract(user_text, history, needs, last_q)
    new_needs = merge_needs(needs, update)
    if update.get("monthly_budget"):
        journey.profile = {**journey.profile, "monthly_budget": update["monthly_budget"]}
    profile = build_profile({**journey.profile, "language": journey.language})

    already_recommended = journey.stage == "recommended"
    informative = bool(update)
    wants_rec = wants_recommendation(user_text)
    nq = next_question(new_needs, bool(profile.monthly_budget), asked)
    ready = wants_rec or already_recommended or nq is None or len(asked) >= MAX_QUESTIONS
    if already_recommended and not informative and "?" in user_text and provider.name != "mock":
        # free-form question after the recommendation: let the LLM answer from the engine's facts only
        rec = build_bundles(profile, new_needs, catalogue)
        facts = {**recommendation_facts(rec, catalogue), "catalogue": [{"name": p.product_name, "description": p.description, "unit": p.unit} for p in catalogue.values()]}
        text = provider.answer(user_text, facts, history, journey.language)
        if text and reply_is_grounded(text, facts, ""):
            return _finish(db, journey, new_needs, text, None, rec, catalogue, provider, profile, replace_selection=False)

    out_needs = {**new_needs, "asked": asked}
    if not ready:
        text = (_ack(update, lang) + " " if update else "") + T.QUESTIONS[lang][nq]
        asked.append(nq)
        out_needs.update(asked=asked, last_question=nq)
        journey.needs = out_needs
        text = text.strip()
        facts = {"question": T.QUESTIONS[lang][nq], "known_needs": {k: v for k, v in new_needs.items() if k not in ("asked", "last_question")}}
        text = _maybe_rephrase(provider, text, facts, history, journey.language)
        db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
        db.commit()
        return {"reply": text, "question": nq, "chips": T.CHIPS[lang].get(nq, []), "recommendation_ready": False, "needs": journey.needs, "provider": provider.name}

    rec = build_bundles(profile, new_needs, catalogue)
    out_needs.update(last_question=None)
    journey.needs = out_needs
    template = render_recommendation(rec, catalogue, lang, profile)
    if update.get("priority") == "price" and already_recommended:
        template = T.CHEAPER[lang] + "\n" + template
    facts = recommendation_facts(rec, catalogue)
    return _finish(db, journey, out_needs, template, facts, rec, catalogue, provider, profile, replace_selection=True)


def _maybe_rephrase(provider: Provider, template: str, facts: dict | None, history: list[dict], language: str) -> str:
    if provider.name == "mock" or facts is None:
        return template
    text = provider.phrase(template, facts, history, language)
    if text and reply_is_grounded(text, facts, template):
        return text
    return template


def _finish(db, journey, needs, text, facts, rec, catalogue, provider, profile, replace_selection: bool) -> dict:
    if facts is not None:
        text = _maybe_rephrase(provider, text, facts, history_of(journey), journey.language)
    tier = rec["tiers"][rec["recommended_tier"]]
    if replace_selection:
        journey.selection = {"items": [{"product_id": i["product_id"], "quantity": i["quantity"]} for i in tier["items"]],
                             "term_months": tier["term_months"], "tier": rec["recommended_tier"]}
        journey.stage = "recommended"
    db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
    db.commit()
    lang = _lang(journey)
    return {"reply": text, "question": None, "chips": ["Make it cheaper", "Add CCTV", "Why do I need failover?"] if lang == "en" else ["सस्ता करें", "CCTV जोड़ें", "फेलओवर क्यों चाहिए?"],
            "recommendation_ready": True, "needs": journey.needs, "provider": provider.name,
            "summary": {"tier": rec["recommended_tier"], "monthly_total": tier["quote"]["totals"]["monthly_total"],
                        "setup_total": tier["quote"]["totals"]["setup_total"], "items": len(tier["items"])}}
