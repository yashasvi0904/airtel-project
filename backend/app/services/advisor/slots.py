"""Structured 'needs' slots, rule-based extraction (English / Hindi / Hinglish) and the question plan.

The question plan is deterministic so the conversation always terminates, whichever provider reads the user's words.
"""
import re

from ..recommender import NEED_PRODUCTS

WANT_KEYWORDS: dict[str, list[str]] = {
    "whatsapp": ["whatsapp", "whats app", "व्हाट्सऐप", "वॉट्सऐप", "व्हॉट्सऐप"],
    "sms": ["sms", "text message", "एसएमएस", "bulk message"],
    "email": ["email", "e-mail", "mail id", "ईमेल", "office suite", "google workspace"],
    "backup": ["backup", "back up", "back-up", "data safe", "बैकअप"],
    "security": ["antivirus", "anti virus", "virus", "ransomware", "malware", "endpoint", "सुरक्षा"],
    "firewall": ["firewall", "फायरवॉल"],
    "cctv": ["cctv", "camera", "cameras", "सीसीटीवी", "कैमरा", "कैमरे"],
    "pos": ["pos", "billing", "invoice", "gst bill", "card machine", "upi", "inventory", "बिलिंग", "बिल"],
    "website": ["website", "web site", "domain", "वेबसाइट"],
    "phone_system": ["ivr", "call centre", "call center", "landline", "phone system", "sip", "telephony", "call recording"],
    "toll_free": ["toll free", "toll-free", "1800"],
    "iot": ["iot", "sensor", "machine monitoring", "monitor machines", "energy use", "machine uptime"],
    "fleet": ["vehicle", "gps", "fleet", "truck", "delivery van", "tracker", "गाड़ी", "वाहन"],
    "failover": ["failover", "backup internet", "standby link", "second connection"],
    "static_ip": ["static ip", "fixed ip"],
    "guest_wifi": ["guest wifi", "guest wi-fi", "customer wifi", "customer wi-fi", "wifi for customers", "wi-fi for customers"],
    "sd_wan": ["sd-wan", "sdwan", "one dashboard", "manage all branches", "central management"],
}
DOWNTIME_WORDS = ["downtime", "outage", "goes down", "keeps going", "disconnect", "unreliable", "slow", "not stable", "नेट बंद", "नेट चला जाता", "धीमा", "बार बार बंद"]
PRICE_WORDS = ["cheap", "cheaper", "afford", "low cost", "tight budget", "budget friendly", "sasta", "सस्ता", "कम खर्च"]
RELIABLE_WORDS = ["reliable", "uptime", "never go down", "mission critical", "भरोसेमंद"]
NOTHING_WORDS = ["nothing else", "no thanks", "that's all", "thats all", "that is all", "none", "no need", "नहीं", "कुछ नहीं", "bas itna", "nahi", "no"]
YES_WORDS = ["yes", "yeah", "yep", "available", "haan", "हाँ", "हां", "ha"]
RECOMMEND_WORDS = ["recommend", "suggest", "show me", "what do you", "bundle", "quote", "price", "plan", "सुझाव", "बताओ", "बताइए"]

NUMBER_PATTERNS = {
    "cameras": r"(\d+)\s*(?:cctv|cameras?|कैमरे?)",
    "mobile_lines": r"(\d+)\s*(?:sims?|lines?|mobile|phones?|numbers?|connections?)",
    "pos_counters": r"(\d+)\s*(?:counters?|pos|billing)",
    "vehicles": r"(\d+)\s*(?:vehicles?|trucks?|vans?|cars?|bikes?)",
    "machines": r"(\d+)\s*(?:machines?|devices?|sensors?)",
}

QUESTIONS = ["pain", "extras", "fibre", "lines", "cameras", "pos", "budget"]


def _has(text: str, words: list[str]) -> bool:
    for w in words:
        if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) if w.isascii() else w in text:
            return True
    return False


def extract_rules(text: str, last_question: str | None) -> dict:
    """Keyword/number extraction used by the mock provider and as a safety net for the LLM provider."""
    t = (text or "").lower().strip()
    out: dict = {}
    wants = [tag for tag, words in WANT_KEYWORDS.items() if _has(t, words)]
    if wants:
        out["wants"] = wants
    for key, pat in NUMBER_PATTERNS.items():
        m = re.search(pat, t)
        if m and 0 < int(m.group(1)) <= 500:
            out[key] = int(m.group(1))
    if re.search(r"no\s+fib(?:re|er)|fib(?:re|er)\s+(?:is\s+)?(?:not|nahi)|not\s+(?:available|feasible)\s+(?:for\s+)?fib|wireless only|no broadband line", t):
        out["fibre_available"] = False
    elif re.search(r"fib(?:re|er)\s+(?:is\s+)?available|have\s+fib(?:re|er)|fib(?:re|er)\s+hai", t):
        out["fibre_available"] = True
    if _has(t, DOWNTIME_WORDS):
        out["pain_downtime"] = True
    if _has(t, PRICE_WORDS):
        out["priority"] = "price"
    elif _has(t, RELIABLE_WORDS):
        out["priority"] = "reliability"
    if re.search(r"only\s+(?:a\s+)?(?:mobile|sim)|just\s+(?:a\s+)?sim|sirf\s+sim", t):
        out["mobile_only"] = True
    budget = re.search(r"(?:budget|spend|pay|afford)[^0-9]{0,20}(?:₹|rs\.?|inr)?\s*([\d,]{3,7})|(?:₹|rs\.?|inr)\s*([\d,]{3,7})", t)
    if budget:
        val = int((budget.group(1) or budget.group(2)).replace(",", ""))
        if 200 <= val <= 1_000_000:
            out["monthly_budget"] = val

    # short answers are interpreted in the context of the question just asked
    short = len(t.split()) <= 4
    if short and last_question:
        yes = _has(t, YES_WORDS) and not _has(t, ["not", "no"])
        no = _has(t, NOTHING_WORDS) and not yes
        if last_question == "fibre":
            if yes:
                out["fibre_available"] = True
            elif no or "not sure" in t:
                out["fibre_available"] = False if no else None
        elif last_question == "extras" and no:
            out["no_more_needs"] = True
        elif last_question in ("lines", "cameras", "pos", "budget") and re.fullmatch(r"[₹rs.\s]*[\d,]+", t):
            val = int(re.sub(r"\D", "", t))
            key = {"lines": "mobile_lines", "cameras": "cameras", "pos": "pos_counters", "budget": "monthly_budget"}[last_question]
            if (key == "monthly_budget" and val >= 200) or (key != "monthly_budget" and 0 < val <= 500):
                out[key] = val
    return {k: v for k, v in out.items() if v is not None}


def wants_recommendation(text: str) -> bool:
    return _has((text or "").lower(), RECOMMEND_WORDS)


def merge_needs(needs: dict, update: dict) -> dict:
    out = dict(needs)
    for k, v in (update or {}).items():
        if k == "wants":
            valid = [w for w in v if w in NEED_PRODUCTS]
            out["wants"] = sorted(set(out.get("wants", [])) | set(valid))
        elif k in ("mobile_lines", "cameras", "pos_counters", "vehicles", "machines", "monthly_budget"):
            if isinstance(v, (int, float)) and v > 0:
                out[k] = int(v)
        elif k in ("fibre_available", "pain_downtime", "mobile_only", "no_more_needs") and isinstance(v, bool):
            out[k] = v
        elif k == "priority" and v in ("price", "reliability"):
            out[k] = v
    return out


def next_question(needs: dict, profile_has_budget: bool, asked: list[str]) -> str | None:
    """The next unanswered question, or None when we know enough."""
    wants = needs.get("wants", [])
    for q in QUESTIONS:
        if q in asked:
            continue
        if q == "pain" and (needs.get("pain_downtime") or needs.get("priority")):
            continue
        if q == "extras" and (wants or needs.get("no_more_needs")):
            continue
        if q == "fibre" and (needs.get("fibre_available") is not None or needs.get("mobile_only")):
            continue
        if q == "lines" and (needs.get("mobile_lines") or needs.get("mobile_only")):
            continue
        if q == "cameras" and not ("cctv" in wants and not needs.get("cameras")):
            continue
        if q == "pos" and not ("pos" in wants and not needs.get("pos_counters")):
            continue
        if q == "budget" and (needs.get("monthly_budget") or profile_has_budget):
            continue
        return q
    return None
