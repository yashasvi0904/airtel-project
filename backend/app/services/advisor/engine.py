"""Advisor turn orchestration: understand -> remember -> (answer | clarify | ask the next relevant question | recommend).

Per user message:
  1. read it (LLM or rules) into structured needs, including what they do NOT want and which link they named;
  2. read short answers ("yes", "nothing", "4") against the question that was just asked;
  3. say back what was understood;
  4. if they asked a question, answer it from the catalogue and quote, then return to the open topic;
  5. otherwise ask the next topic that matters for this business (slots.next_question) or, when enough is known / they ask, recommend.
Products, prices and eligibility always come from the deterministic engine; the LLM only interprets and phrases.
"""
import re

from sqlalchemy.orm import Session

from ...models import AdvisorMessage, Journey, Product
from .. import i18n
from ..profile import build_profile
from ..recommender import NEED_LABEL, build_bundles
from . import qa
from . import templates as T
from .providers import Provider, get_provider, reply_is_grounded
from .slots import MAX_QUESTIONS, mark_declined, merge_needs, next_question, wants_recommendation

MAX_QUESTIONS_ASKED = MAX_QUESTIONS + 1  # topics + a quantity follow-up or two, never an interrogation
CONN_LABEL = {"fibre": i18n.tx("fibre broadband"), "5g": i18n.tx("a 5G wireless link"), "leased_line": i18n.tx("a dedicated leased line")}
CURRENT_PHRASE = {"Mobile hotspot": i18n.tx("a mobile hotspot"), "Home broadband": i18n.tx("home broadband"), "Business broadband": i18n.tx("business broadband"),
                  "Leased line": i18n.tx("a leased line"), "Mixed per site": i18n.tx("different internet providers at different sites"), "None": i18n.tx("no regular internet connection")}
FINISHED = [r"(?:i|we)\s+(?:do\s*n[o']?t|dont)\s+need\s+(?:any\s*thing|anything|more|else|any)", r"no\s+(?:more|other)\s+needs?", r"nothing\s+(?:more|else)", r"that'?s\s+(?:all|it)",
            r"that\s+is\s+(?:all|enough)", r"\benough\b", r"mujhe\s+kuch\s+nahi", r"कुछ\s+नहीं\s+चाहिए", r"बस\s+इतना", r"bas\s+itna"]


def _lang(journey: Journey) -> str:
    return i18n.normalize(journey.language)  # one of the ten supported languages; unknown codes read as English


def _fmt(n: float) -> str:
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


def history_of(journey: Journey) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in journey.messages]


def is_finished(text: str) -> bool:
    """'that's all' / 'nothing else' / 'I don't need anything else': stop asking and recommend. (A bare 'nothing' is only an answer to one topic.)"""
    t = (text or "").lower()
    return any(re.search(p, t) for p in FINISHED) and not re.search(r"\d", t)


def question_text(lang: str, q: str, profile) -> str:
    current = CURRENT_PHRASE.get(getattr(profile, "current_internet", ""), i18n.tx("your current internet"))
    return T.QUESTIONS[lang][q].format(current=i18n.tr(current, lang))


def understood(needs: dict, lang: str) -> list[str]:
    """What the customer has told us, in their language - shown back to them and used to explain the recommendation."""
    out: list[str] = []
    if needs.get("connectivity"):
        out.append(i18n.tr(CONN_LABEL[needs["connectivity"]], lang))
    elif needs.get("fibre_available") is False:
        out.append(i18n.tr("no fibre line at your site", lang))
    out += [i18n.tr(NEED_LABEL.get(w, w), lang) for w in needs.get("wants", [])]
    for key, tpl in (("cameras", "{n} cameras"), ("mobile_lines", "{n} mobile lines"), ("pos_counters", "{n} billing counters"), ("vehicles", "{n} vehicles"), ("machines", "{n} machines")):
        if needs.get(key):
            out.append(i18n.tr(tpl, lang, n=needs[key]))
    if needs.get("rejects"):
        out.append(i18n.tr("without {items}", lang, items=", ".join(i18n.tr(NEED_LABEL.get(w, w), lang) for w in needs["rejects"])))
    if needs.get("monthly_budget"):
        out.append(i18n.tr("a budget of {amount}/month", lang, amount=f"₹{_fmt(needs['monthly_budget'])}"))
    if needs.get("pain_downtime"):
        out.append(i18n.tr("the internet going down is a problem", lang))
    elif needs.get("pain_slow"):
        out.append(i18n.tr("slow speed is a problem", lang))
    if needs.get("priority") == "price":
        out.append(i18n.tr("keeping the cost low", lang))
    elif needs.get("priority") == "reliability":
        out.append(i18n.tr("reliability above all", lang))
    return out


def _ack(update: dict, lang: str) -> str:
    items = understood(update, lang)
    return i18n.tr("Noted: {items}.", lang, items=", ".join(items)) if items else ""


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


def render_recommendation(rec: dict, catalogue: dict[str, Product], lang: str, profile, needs: dict | None = None) -> str:
    name = rec["recommended_tier"]
    tier = rec["tiers"][name]
    q = tier["quote"]
    lines = [T.REC_HEAD[lang].format(tier=T.TIER_NAMES[lang][name])]
    noted = understood(needs or {}, lang)
    if noted:
        lines.append(i18n.tr("What you told me: {items}.", lang, items=", ".join(noted)))
    for it in tier["items"]:
        p = catalogue[it["product_id"]]
        line_q = next((l for l in q["items"] if l["product_id"] == p.product_id), None)
        price = f" - ₹{_fmt(line_q['monthly'])}{i18n.tr('/mo', lang)}" if line_q else ""
        lines.append(f"• {p.product_name} × {it['quantity']} ({i18n.localize(p.unit, lang)}){price}: {i18n.localize(it['reasons'][0], lang)}")
    t = q["totals"]
    lines.append("")
    lines.append(T.REC_TOTAL[lang].format(monthly=_fmt(t["monthly_total"]), gst=_fmt(t["gst_rate_percent"]), setup=_fmt(t["setup_total"]),
                                          term=t["term_months"], first=_fmt(t["first_payment"])))
    for a in rec.get("assumptions", []):
        if a["type"] == "sims":
            lines.append(i18n.tr("I assumed {n} business SIM(s) for your {employees} staff - tell me if you need a different number.", lang, n=a["n"], employees=a["employees"]))
    if rec.get("budget"):
        key = T.BUDGET_OVER if rec["over_budget"] else T.BUDGET_OK
        lines.append(key[lang].format(budget=_fmt(rec["budget"])))
    if "vs_current_spend" in t and abs(t["vs_current_spend"]) >= 1:
        d = t["vs_current_spend"]
        word = i18n.tr("more" if d > 0 else "less", lang)
        lines.append(T.SAVINGS[lang].format(cur=_fmt(t["current_monthly_spend"]), diff=_fmt(abs(d)), dir=word))
    if rec["excluded"]:
        items = "; ".join(
            f"{i18n.localize(e['name'], lang)} ({i18n.localize(e['eligibility']['reasons'][0]['message'], lang).rstrip('.')}"
            + (f" - {i18n.tr('{step} to unlock.', lang, step=i18n.localize(e['eligibility']['unlock'][0], lang)).rstrip('.')}" if e["eligibility"]["unlock"] else "") + ")"
            for e in rec["excluded"][:3] if e["eligibility"]["reasons"])
        if items:
            lines.append(T.EXCLUDED[lang].format(items=items))
    lines.append(T.NEXT_STEP[lang])
    return "\n".join(lines)


def _state(journey: Journey, lang: str, needs: dict | None = None) -> dict:
    n = needs if needs is not None else (journey.needs or {})
    return {"needs": journey.needs, "understood": understood(n, lang), "progress": {"asked": len(n.get("asked", [])), "max": MAX_QUESTIONS_ASKED}}


def resume_state(journey: Journey) -> dict:
    """What a returning customer needs to continue: the summary so far, progress, and the chips for the question still open."""
    lang = _lang(journey)
    q = (journey.needs or {}).get("last_question")
    return {**_state(journey, lang), "question": q, "chips": T.chips_for(lang, q) if q and journey.stage != "recommended" else _post_rec_chips(lang) if journey.stage == "recommended" else []}


def start(db: Session, journey: Journey) -> dict:
    """First assistant message, built from the onboarding profile."""
    lang = _lang(journey)
    p = build_profile({**journey.profile, "language": journey.language})
    name = f", {p.contact_name.split()[0]}" if p.contact_name else ""
    needs = dict(journey.needs or {})
    asked = list(needs.get("asked", []))
    q = next_question(needs, bool(p.monthly_budget), asked, p)
    text = T.GREETING[lang].format(name=name, biz=p.business_name or p.business_type or "your business", city=p.city or "your city",
                                   emp=p.employees, sites=p.sites)
    if q:
        text += "\n\n" + question_text(lang, q, p)
        asked.append(q)
        needs.update(asked=asked, last_question=q)
        journey.needs = needs
    db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
    journey.stage = "advising"
    db.commit()
    return {"reply": text, "question": q, "chips": T.chips_for(lang, q) if q else [], "recommendation_ready": False, "provider": get_provider().name, **_state(journey, lang)}


def turn(db: Session, journey: Journey, user_text: str, catalogue: dict[str, Product], provider: Provider | None = None) -> dict:
    provider = provider or get_provider()
    lang = _lang(journey)
    needs = dict(journey.needs or {})
    asked = list(needs.get("asked", []))
    last_q = needs.get("last_question")
    history = history_of(journey)
    db.add(AdvisorMessage(journey_id=journey.id, role="user", content=user_text))

    if qa.is_goodbye(user_text):
        # the customer is leaving: close politely, do NOT ask another question or touch their saved plan
        text = qa.farewell(lang)
        db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
        db.commit()
        chips = ["मेरा सुझाव दिखाएँ"] if lang == "hi" else ["Show my recommendation"]
        return {"reply": text, "question": None, "chips": chips, "recommendation_ready": journey.stage == "recommended", "provider": provider.name, **_state(journey, lang)}

    update = provider.extract(user_text, history, needs, last_q)
    if qa.social_reply(user_text, lang):
        update = {}  # "hi" / "thanks" carry no needs, whatever an LLM read into the earlier history
    if set(update) <= {"wants"} and qa.is_info_question(user_text):
        update = {}  # "what is CCTV?" asks about a product; it is not a request to add it
    clarify, declined, unsure = update.get("_clarify"), update.get("_declined"), update.get("_unsure")
    update = {k: v for k, v in update.items() if not k.startswith("_")}  # reading hints, not facts

    new_needs = merge_needs(needs, update)
    if declined:
        new_needs = mark_declined(new_needs, declined)  # 'nothing' to a topic: do not ask again and do not guess
    if update.get("monthly_budget"):
        journey.profile = {**journey.profile, "monthly_budget": update["monthly_budget"]}
    profile = build_profile({**journey.profile, "language": journey.language})

    already_recommended = journey.stage == "recommended"
    finished = is_finished(user_text)
    wants_rec = wants_recommendation(user_text) or finished
    if finished:
        new_needs = {**new_needs, "no_more_needs": True}
    informative = bool(update) or bool(declined) or bool(unsure) or bool(clarify)

    if clarify and clarify in needs.get("clarified", []):
        new_needs, declined, clarify = mark_declined(new_needs, clarify), clarify, None  # asked "which ones?" already: a second vague yes means nothing specific
    if clarify and not finished:
        # a bare "yes" to an open question ("do you need WhatsApp, SMS, billing...?"): ask WHICH, do not guess and do not move on
        text = (_ack(update, lang) + " " if update else "") + T.CLARIFY[lang][clarify]
        new_needs = {**new_needs, "clarified": sorted(set(new_needs.get("clarified", [])) | {clarify})}
        journey.needs = {**new_needs, "asked": asked, "last_question": last_q}
        db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text.strip()))
        db.commit()
        return {"reply": text.strip(), "question": clarify, "chips": T.chips_for(lang, clarify), "recommendation_ready": False, "provider": provider.name, **_state(journey, lang, new_needs)}

    nq = next_question(new_needs, bool(profile.monthly_budget), asked, profile)
    ready = wants_rec or already_recommended or nq is None or len(asked) >= MAX_QUESTIONS_ASKED

    if not informative:
        # The message states no new need: answer what the customer actually said instead of replaying the script.
        side = _side_reply(db, journey, user_text, new_needs, profile, catalogue, provider, history, last_q, already_recommended, wants_rec)
        if side:
            return side

    out_needs = {**new_needs, "asked": asked}
    if not ready:
        thanks = i18n.tr("Thanks, that helps.", lang) + " " if (not update and not informative and last_q and len(user_text.split()) > 4) else ""  # described it in their own words
        text = thanks + ((_ack(update, lang) + " ") if update else "") + question_text(lang, nq, profile)
        asked.append(nq)
        out_needs.update(asked=asked, last_question=nq)
        journey.needs = out_needs
        text = text.strip()
        facts = {"question": question_text(lang, nq, profile), "known_needs": {k: v for k, v in new_needs.items() if k not in ("asked", "last_question")}}
        text = _maybe_rephrase(provider, text, facts, history, journey.language)
        db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
        db.commit()
        return {"reply": text, "question": nq, "chips": T.chips_for(lang, nq), "recommendation_ready": False, "provider": provider.name, **_state(journey, lang, out_needs)}

    rec = build_bundles(profile, new_needs, catalogue)
    out_needs.update(last_question=None)
    journey.needs = out_needs
    template = render_recommendation(rec, catalogue, lang, profile, new_needs)
    if update.get("priority") == "price" and already_recommended:
        template = T.CHEAPER[lang] + "\n" + template
    facts = recommendation_facts(rec, catalogue)
    return _finish(db, journey, out_needs, template, facts, rec, catalogue, provider, profile, replace_selection=True)


def _is_short_answer(text: str, last_q: str | None) -> bool:
    """'not sure', '4', 'ok' ... replies to the question just asked; the normal flow handles them."""
    return bool(last_q) and len(text.split()) <= 4


def _side_reply(db, journey, user_text, needs, profile, catalogue, provider, history, last_q, already_recommended, wants_rec) -> dict | None:
    """Answer a free-form message (question, chit-chat, off-script) from the catalogue and the engine's own numbers.

    LLM provider first (output must pass reply_is_grounded), then the deterministic rules answerer, then an honest
    'here is what I can do'. Returns None when the normal question/recommendation flow should handle the message."""
    lang = _lang(journey)
    if is_finished(user_text):
        return None  # handled by the main flow: stop asking and build the bundle
    if wants_rec and re.search(r"recommend|suggest|show me|bundle|सुझाव", user_text, re.I) and not qa.is_info_question(user_text):
        return None  # an explicit request for the bundle goes to the engine, never to free-form chat
    rec = build_bundles(profile, needs, catalogue) if already_recommended else None
    text: str | None = qa.social_reply(user_text, lang)  # greetings / thanks: deterministic, never an LLM improvisation
    if text is None and provider.name != "mock":
        facts = {**(recommendation_facts(rec, catalogue) if rec else {"known_needs": {k: v for k, v in needs.items() if k not in ("asked", "last_question")}}),
                 "catalogue": [{"name": p.product_name, "description": p.description, "unit": p.unit, "list_price_range_inr_per_month": [p.price_min, p.price_max]}
                               for p in catalogue.values()]}
        llm = provider.answer(user_text, facts, history, journey.language)
        # the engine, not the model, recommends: an answer that pitches products before a bundle exists is discarded
        if llm and reply_is_grounded(llm, facts, "") and (rec or not re.search(r"\brecommend|\bi suggest\b|\bi'd suggest\b|\bbest option\b", llm, re.I)):
            text = llm
    if not text:
        text = qa.answer_rules(user_text, catalogue, rec, lang)
    if not text and not wants_rec and not last_q and not already_recommended:
        text = T.FALLBACK_HELP[lang]  # only when there is no open question to hang the message on
    if not text:
        return None

    if already_recommended:
        # keep the customer's selection untouched; just answer
        db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
        db.commit()
        return {"reply": text, "question": None, "chips": _post_rec_chips(lang), "recommendation_ready": True, "provider": provider.name, **_state(journey, lang)}
    # still gathering needs: answer, then bring back the question that is still open
    chips: list[str] = []
    if last_q:
        if not text.rstrip().endswith("?"):  # never stack two questions in one reply
            text = f"{text}\n\n{question_text(lang, last_q, profile)}"
        chips = T.chips_for(lang, last_q)
    db.add(AdvisorMessage(journey_id=journey.id, role="assistant", content=text))
    db.commit()
    return {"reply": text, "question": last_q, "chips": chips, "recommendation_ready": False, "provider": provider.name, **_state(journey, lang)}


def _post_rec_chips(lang: str) -> list[str]:
    return ["Make it cheaper", "Add CCTV", "Why do I need failover?"] if lang != "hi" else ["सस्ता करें", "CCTV जोड़ें", "फेलओवर क्यों चाहिए?"]


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
    return {"reply": text, "question": None, "chips": _post_rec_chips(lang),
            "recommendation_ready": True, "provider": provider.name, **_state(journey, lang, needs),
            "summary": {"tier": rec["recommended_tier"], "monthly_total": tier["quote"]["totals"]["monthly_total"],
                        "setup_total": tier["quote"]["totals"]["setup_total"], "items": len(tier["items"])}}
