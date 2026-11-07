"""Deterministic conversational answers for messages that carry no new 'need'.

Used when no LLM key is configured, and as the fallback when the LLM reply is rejected. Every fact comes from the
product catalogue or from the engine's own recommendation/quote (rec), so nothing here can drift from the pricing
engine. If a question cannot be answered from those, it says so instead of guessing.
"""
import re

from ...models import Product
from ..recommender import NEED_PRODUCTS
from .slots import WANT_KEYWORDS, _has

# connectivity products have no "want" tag, so they get their own vocabulary
EXTRA_PRODUCT_WORDS: dict[str, list[str]] = {
    "P01": ["fibre 100", "fiber 100"], "P02": ["fibre 300", "fiber 300"], "P03": ["fibre 1g", "gigabit"],
    "P04": ["airfiber", "air fiber", "5g fwa", "wireless broadband"],
    "P05": ["leased line 20"], "P06": ["leased line", "dedicated internet"],
    "P07": ["postpaid 299", "299 plan"], "P08": ["postpaid 599", "599 plan"],
}
GENERIC_WORDS = {
    "fibre": ["P01", "P02", "P03"], "fiber": ["P01", "P02", "P03"], "broadband": ["P01", "P02", "P03"],
    "leased line": ["P05", "P06"], "sim": ["P07", "P08"], "postpaid": ["P07", "P08"], "mobile plan": ["P07", "P08"],
}
PID_TO_TAG = {pid: tag for tag, pid in NEED_PRODUCTS.items()}

T = {
    "greet": {
        "en": "Hello! I'm your Accel Business advisor. Tell me what your business needs - for example '4 cameras', 'WhatsApp for customers' or 'internet keeps dropping' - and I'll build a bundle with a clear monthly price.",
        "hi": "नमस्ते! मैं आपका Accel Business सलाहकार हूँ। बताइए आपके बिज़नेस को क्या चाहिए - जैसे '4 कैमरे', 'ग्राहकों के लिए WhatsApp' या 'इंटरनेट बार-बार बंद' - मैं साफ़ मासिक कीमत वाला बंडल बना दूँगा।",
    },
    "thanks": {"en": "You're welcome! Anything else you'd like to know or add to the bundle?", "hi": "आपका स्वागत है! और कुछ जानना या बंडल में जोड़ना हो तो बताइए।"},
    "bye": {"en": "No problem - thanks for stopping by! Your progress is saved. Say 'recommend' whenever you'd like to see a bundle, or just come back any time.",
            "hi": "कोई बात नहीं - धन्यवाद! आपका प्लान सेव है। जब चाहें 'recommend' लिखकर बंडल देख लें, या कभी भी वापस आइए।"},
    "help": {
        "en": "I can help you pick the right mix from Accel Business's range: {cats}. Describe your business needs in your own words, ask about any product (e.g. 'what is Cloud CCTV?'), or - once you have a bundle - ask about its price, setup, contract or GST.",
        "hi": "मैं Accel Business की रेंज से सही मिक्स चुनने में मदद करता हूँ: {cats}। अपनी ज़रूरत अपने शब्दों में बताइए, किसी भी प्रोडक्ट के बारे में पूछिए (जैसे 'Cloud CCTV क्या है?'), या बंडल बनने के बाद उसकी कीमत, सेटअप, कॉन्ट्रैक्ट या GST पूछिए।",
    },
    "unknown": {
        "en": "I don't have an answer for that in our catalogue, and I'd rather not guess. I can explain any product, tell you your bundle's price, setup, contract and GST, or add things you need.",
        "hi": "इसका जवाब मेरे पास कैटलॉग में नहीं है और मैं अंदाज़ा नहीं लगाना चाहता। मैं किसी भी प्रोडक्ट के बारे में बता सकता हूँ, बंडल की कीमत, सेटअप, कॉन्ट्रैक्ट और GST बता सकता हूँ, या आपकी ज़रूरत की चीज़ें जोड़ सकता हूँ।",
    },
    "no_rec": {
        "en": "I'll be able to give exact prices once I have a few more details - or say 'recommend' and I'll build a bundle right now.",
        "hi": "कुछ और जानकारी मिलते ही मैं सटीक कीमत बता पाऊँगा - या 'recommend' लिखें, मैं अभी बंडल बना देता हूँ।",
    },
    "process": {
        "en": "After this chat: you review the bundle and quote, complete a digital KYC by uploading your business and ID documents (they are read and checked automatically, no branch visit), pay, and book an installation slot. Documents are encrypted and deleted after the retention period.",
        "hi": "इस चैट के बाद: आप बंडल और कोटेशन देखते हैं, बिज़नेस और ID डॉक्यूमेंट अपलोड करके डिजिटल KYC करते हैं (अपने-आप पढ़े और जाँचे जाते हैं, ब्रांच जाने की ज़रूरत नहीं), भुगतान करते हैं और इंस्टॉलेशन स्लॉट बुक करते हैं। डॉक्यूमेंट एन्क्रिप्टेड रहते हैं और रिटेंशन अवधि के बाद हटा दिए जाते हैं।",
    },
    "human": {
        "en": "I can't see support hours or call-back options in our catalogue, so I won't guess. I can keep helping with the bundle; support details are confirmed when you finish the quote.",
        "hi": "सपोर्ट के समय या कॉल-बैक की जानकारी मेरे कैटलॉग में नहीं है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा। बंडल में मदद जारी रख सकता हूँ।",
    },
}


def _m(n: float) -> str:
    return f"₹{n:,.0f}" if float(n).is_integer() else f"₹{n:,.2f}"


def _say(key: str, lang: str, **kw) -> str:
    d = T[key]
    return d.get(lang, d["en"]).format(**kw)


def _tier(rec: dict | None) -> dict | None:
    return rec["tiers"][rec["recommended_tier"]] if rec else None


def find_products(text: str, catalogue: dict[str, Product]) -> list[str]:
    """Product ids the customer is talking about (by need keyword, product name, or connectivity vocabulary)."""
    t = text.lower()
    found: list[str] = []

    def add(pid: str) -> None:
        if pid in catalogue and pid not in found:
            found.append(pid)

    for tag, words in WANT_KEYWORDS.items():
        if _has(t, words) and tag in NEED_PRODUCTS:
            add(NEED_PRODUCTS[tag])
    for pid, words in EXTRA_PRODUCT_WORDS.items():
        if _has(t, words):
            add(pid)
    for pid, p in catalogue.items():
        if p.product_name.lower() in t:
            add(pid)
    if not found:
        for w, pids in GENERIC_WORDS.items():
            if _has(t, [w]):
                for pid in pids:
                    add(pid)
    return found[:3]


def _in_bundle(pid: str, rec: dict | None) -> dict | None:
    tier = _tier(rec)
    return next((i for i in tier["items"] if i["product_id"] == pid), None) if tier else None


def explain_product(pid: str, catalogue: dict[str, Product], rec: dict | None, lang: str) -> str:
    p = catalogue[pid]
    out = [f"**{p.product_name}** - {p.description.rstrip('.')}. Priced {p.unit}."]
    item = _in_bundle(pid, rec)
    tier = _tier(rec)
    if item and tier and tier.get("quote"):
        line = next((l for l in tier["quote"]["items"] if l["product_id"] == pid), None)
        price = f" at {_m(line['monthly'])}/month" if line else ""
        out.append(f"It's in your bundle (× {item['quantity']}){price}: {item['reasons'][0]}")
        return " ".join(out)
    blocked = next((e for e in (rec or {}).get("excluded", []) if e.get("product_id") == pid), None)
    if blocked and blocked["eligibility"]["reasons"]:
        why = blocked["eligibility"]["reasons"][0]["message"].rstrip(".")
        unlock = blocked["eligibility"]["unlock"]
        out.append(f"It's not available for you right now: {why}." + (f" To unlock: {unlock[0]}." if unlock else ""))
        return " ".join(out)
    rng = f"{_m(p.price_min)}-{_m(p.price_max)}" if p.price_min != p.price_max else _m(p.price_min)
    setup = f", {_m(p.setup_fee)} one-time setup per unit" if p.setup_fee else ", no setup fee"
    out.append(f"List price range {rng}/month{setup}; minimum contract {p.min_contract_months} months. "
               "The exact price in your bundle depends on quantity and term." + (" Say you need it and I'll add it." if rec else ""))
    return " ".join(out)


def _totals(rec: dict) -> dict | None:
    tier = _tier(rec)
    return tier["quote"]["totals"] if tier and tier.get("quote") else None


GOODBYE_WORDS = ["bye", "bye bye", "goodbye", "good bye", "see you", "see ya", "talk later", "not interested", "leave it", "never mind", "nevermind",
                 "alvida", "chalta hu", "chalta hoon", "फिर मिलते", "अलविदा"]
DECLINE_PHRASES = [r"(?:i|we)\s+(?:do\s*n[o']?t|dont)\s+need\s+(?:any\s*thing|anything|more|else|any)", r"no\s+(?:more|other)\s+needs?", r"nothing\s+(?:more|else)",
                   r"that'?s\s+all", r"that\s+is\s+all", r"\bnothing\b", r"mujhe\s+kuch\s+nahi", r"कुछ\s+नहीं\s+चाहिए", r"बस\s+इतना"]
NEED_CUES = ["i need", "i want", "we need", "we want", "add", "require", "looking for", "get me", "chahiye", "chahie", "चाहिए", "जोड़", "लगवा"]
_ASKING_NEED = re.compile(r"\b(?:do|does|did|should|would|will|why do|why should|why would|what do|how do|how much do)\s+(?:i|we)\s+(?:really\s+)?(?:need|want)\b")
INFO_STARTS = r"(what|why|how|which|when|where|who|tell me|explain|kya|kitna|kaise|kyun|क्या|कितना|कैसे|क्यों)\b"


def is_info_question(text: str) -> bool:
    """A question *about* something ('what is CCTV?', 'why failover?') rather than a request for it ('add CCTV')."""
    t = (text or "").lower().strip()
    asks = bool(re.match(INFO_STARTS, t)) or t.endswith("?")
    t = _ASKING_NEED.sub("", t)  # "why do I need X?" is a question, not a request
    return asks and not _has(t, NEED_CUES)


def is_goodbye(text: str) -> bool:
    """The customer is leaving ('bye', 'not interested'). Never answered with another question."""
    t = (text or "").lower().strip()
    return _has(t, GOODBYE_WORDS) and not _has(t, ["i need", "we need", "i want", "we want", "add", "chahiye", "चाहिए"])


def is_decline(text: str) -> bool:
    """'I don't need anything (else)' / 'nothing' - no more needs, so stop asking and recommend."""
    t = (text or "").lower().strip()
    return any(re.search(p, t) for p in DECLINE_PHRASES) and not re.search(r"\d", t)


def farewell(lang: str = "en") -> str:
    return _say("bye", lang)


def social_reply(text: str, lang: str = "en") -> str | None:
    """Greetings, thanks and goodbyes are answered deterministically (no LLM): short, safe and never a made-up recommendation."""
    t = (text or "").lower().strip()
    words = t.split()
    if len(words) <= 5 and _has(t, ["hi", "hello", "hey", "hii", "namaste", "good morning", "good evening", "नमस्ते", "हेलो"]):
        return _say("greet", lang)
    if len(words) <= 6 and _has(t, ["thanks", "thank you", "thx", "shukriya", "dhanyavad", "धन्यवाद", "शुक्रिया"]):
        return _say("thanks", lang)
    return None


def answer_rules(text: str, catalogue: dict[str, Product], rec: dict | None, lang: str = "en") -> str | None:
    """A grounded reply to a message that carries no new needs, or None if nothing matched."""
    t = (text or "").lower().strip()
    if not t:
        return None
    words = t.split()
    tier, totals = _tier(rec), (_totals(rec) if rec else None)
    is_q = "?" in t or bool(re.match(r"(what|why|how|which|when|where|who|can|do|does|is|are|will|kya|kitna|kaise|kyun|क्या|कितना|कैसे|क्यों)\b", t))

    social = social_reply(t, lang)
    if social:
        return social
    if is_goodbye(t):
        return farewell(lang)

    # what is / tell me about a product
    pids = find_products(t, catalogue)
    asks_info = is_q or _has(t, ["tell me", "explain", "details", "about", "include", "includes", "know more", "samjhao", "बताओ", "बताइए", "समझाओ"])
    if pids and asks_info and not _has(t, ["recommend", "suggest"]):
        return "\n\n".join(explain_product(pid, catalogue, rec, lang) for pid in pids[:2])

    if _has(t, ["what can you do", "what do you do", "what do you offer", "what do you sell", "what you offer", "what services", "what products",
                "help", "who are you", "how does this work", "how do you work", "catalogue", "catalog", "क्या कर सकते", "मदद"]):
        cats = ", ".join(dict.fromkeys(p.category for p in catalogue.values()))
        return _say("help", lang, cats=cats)

    if _has(t, ["why this", "why these", "why did you", "why are you recommending", "what's included", "whats included", "what is included",
                "what do i get", "what is in", "what's in", "list", "items", "contents", "kya kya"]) and tier:
        lines = [f"• {catalogue[i['product_id']].product_name} × {i['quantity']}: {i['reasons'][0]}" for i in tier["items"]]
        return "Here is what's in your bundle and why:\n" + "\n".join(lines)

    if _has(t, ["gst", "tax", "taxes"]):
        if totals:
            return (f"GST of {totals['gst_rate_percent']:g}% is included in the totals I quoted (monthly {_m(totals['monthly_total'])}, "
                    f"setup {_m(totals['setup_total'])}). The catalogue lists prices before GST, so the rate is a configurable assumption.")
        return "Catalogue prices are shown before GST; the final quote adds GST at the configured rate and shows it as a separate line."

    if _has(t, ["setup", "set up", "installation", "install", "installed", "how long", "when will", "activate", "activation", "go live", "इंस्टॉल", "सेटअप"]):
        if tier and totals:
            days = max((catalogue[i["product_id"]].install_days for i in tier["items"]), default=0)
            slow = [catalogue[i["product_id"]].product_name for i in tier["items"] if catalogue[i["product_id"]].install_days == days][:2]
            return (f"One-time setup for your bundle is {_m(totals['setup_total'])} (incl. GST). Typical installation takes up to {days} days, "
                    f"the longest being {' and '.join(slow)}. You pick an installation slot after checkout.")
        return "Each product has a one-time setup fee and a typical install time (usually a few days); I'll total them for your bundle once it's built. " + _say("no_rec", lang)

    if _has(t, ["contract", "lock in", "lock-in", "lockin", "commitment", "term", "months", "tenure", "cancel", "exit", "कॉन्ट्रैक्ट"]):
        if tier:
            longest = max((catalogue[i["product_id"]].min_contract_months for i in tier["items"]), default=12)
            return (f"Your bundle is on one {tier['term_months']}-month contract; the longest minimum among its products is {longest} months. "
                    "A longer term lowers the monthly price; you can compare terms on the quote page.")
        return "Every product has a minimum contract (typically 12 months) and a longer term lowers the price. I'll show the exact term with your bundle."

    if _has(t, ["how much", "price", "cost", "total", "monthly", "per month", "charges", "bill", "expensive", "kitna", "कितना", "कीमत"]) or (is_q and _has(t, ["pay"])):
        if totals:
            line = f"Your bundle is {_m(totals['monthly_total'])}/month incl. GST, plus {_m(totals['setup_total'])} one-time setup, on a {totals['term_months']}-month term. First payment: {_m(totals['first_payment'])}."
            if rec.get("budget"):
                line += " " + ("That's above" if rec.get("over_budget") else "That's within") + f" your {_m(rec['budget'])} budget."
            return line + " Say 'make it cheaper' to re-plan around cost."
        return None  # let the normal flow build a bundle

    if _has(t, ["why not", "not available", "can't i", "cannot i", "why can't", "why cant", "unavailable", "not eligible", "eligible"]) and rec and rec.get("excluded"):
        lines = []
        for e in rec["excluded"][:4]:
            r = e["eligibility"]["reasons"]
            if r:
                lines.append(f"• {e['name']}: {r[0]['message'].rstrip('.')}" + (f" - to unlock: {e['eligibility']['unlock'][0]}" if e["eligibility"]["unlock"] else ""))
        if lines:
            return "These aren't available for you right now:\n" + "\n".join(lines)

    if _has(t, ["kyc", "documents", "document", "aadhaar", "pan", "gstin", "udyam", "proof", "how do i buy", "how to buy", "checkout", "next step", "what next", "what now", "sign up", "get started", "proceed", "buy"]):
        return _say("process", lang)

    if _has(t, ["support", "customer care", "helpline", "human", "agent", "call me", "callback", "talk to", "speak to", "24x7", "24/7", "night"]):
        return _say("human", lang)

    if is_q and len(words) >= 3:
        return _say("unknown", lang)
    return None


def _merge_generated_qa() -> None:
    import json
    from pathlib import Path

    f = Path(__file__).resolve().parents[2] / "data" / "advisor_i18n.json"
    if not f.exists():
        return
    for lang, names in json.loads(f.read_text(encoding="utf-8")).items():
        for key, text in (names.get("QA") or {}).items():
            if key in T and not (lang == "hi" and "hi" in T[key]):
                T[key][lang] = text


_merge_generated_qa()
