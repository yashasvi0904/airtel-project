"""What the customer means, and what to ask next.

Two jobs, both deterministic so the conversation always makes sense and always terminates, whichever provider (rules or LLM) reads the words:

1. `extract_rules(text, last_question)` turns a message (English / Hindi / Hinglish) into structured needs: what they want, what they
   explicitly do NOT want, which kind of internet link, quantities, budget, and how to read a bare "yes"/"no" given the question just asked.
2. `next_question(needs, ...)` is the discovery plan: it picks the next topic worth asking for THIS business (its segment, its current
   setup), skips anything already answered or declined, and never repeats a question.
"""
import re

from ..recommender import NEED_PRODUCTS

# ---------------------------------------------------------------- vocabulary
WANT_KEYWORDS: dict[str, list[str]] = {
    "whatsapp": ["whatsapp", "whats app", "whatsap", "wa business", "व्हाट्सऐप", "वॉट्सऐप", "व्हॉट्सऐप", "व्हाट्सएप"],
    "sms": ["sms", "text message", "text messages", "bulk message", "bulk messages", "appointment reminder", "appointment reminders", "reminders to customers", "एसएमएस"],
    "email": ["email", "e-mail", "emails", "mail id", "official mail", "company email", "domain email", "office suite", "google workspace", "ईमेल"],
    "backup": ["backup", "back up", "back-up", "data safe", "cloud storage", "save our data", "save my data", "बैकअप"],
    "security": ["antivirus", "anti virus", "anti-virus", "virus", "ransomware", "malware", "hackers", "endpoint", "cyber security", "cybersecurity", "data security", "सुरक्षा"],
    "firewall": ["firewall", "फायरवॉल"],
    "cctv": ["cctv", "camera", "cameras", "camere", "kamere", "kamra", "camra", "security camera", "surveillance", "सीसीटीवी", "कैमरा", "कैमरे"],
    "pos": ["pos", "billing", "invoice", "invoicing", "gst bill", "gst billing", "card machine", "card swipe", "point of sale", "inventory", "billing software", "बिलिंग", "बिल"],
    "website": ["website", "web site", "domain name", "online presence", "वेबसाइट"],
    "phone_system": ["ivr", "call centre", "call center", "landline", "phone system", "sip", "telephony", "call recording", "call routing"],
    "toll_free": ["toll free", "toll-free", "tollfree", "1800"],
    "iot": ["iot", "sensor", "sensors", "machine monitoring", "monitor machines", "monitor my machines", "energy use", "machine uptime", "machine downtime"],
    "fleet": ["vehicle", "vehicles", "gps", "fleet", "truck", "trucks", "delivery van", "delivery vans", "tracker", "vehicle tracking", "गाड़ी", "वाहन"],
    "failover": ["failover", "backup internet", "backup link", "standby link", "second connection", "internet never goes down", "never go down", "dual connection"],
    "static_ip": ["static ip", "fixed ip"],
    "guest_wifi": ["guest wifi", "guest wi-fi", "customer wifi", "customer wi-fi", "wifi for customers", "wi-fi for customers", "wifi", "wi-fi", "wi fi", "वाईफाई", "वाई-फाई"],
    "sd_wan": ["sd-wan", "sdwan", "one dashboard", "manage all branches", "central management", "all branches on one", "different isp", "different isps", "multiple isp", "multiple isps",
               "many isps", "different providers", "multiple providers", "separate bills", "one bill for all", "single bill", "all outlets", "all branches", "all stores", "every outlet", "every branch", "every store"],
}
# a kind of internet link the customer names
CONNECTIVITY_WORDS: dict[str, list[str]] = {
    "leased_line": ["leased line", "lease line", "dedicated internet", "dedicated line", "dedicated bandwidth"],
    "5g": ["5g", "airfiber", "air fiber", "air-fiber", "fwa", "wireless internet", "wireless broadband"],
    "fibre": ["fibre", "fiber", "ftth", "फाइबर", "फ़ाइबर", "ब्रॉडबैंड", "broadband"],
}
DOWNTIME_WORDS = ["downtime", "outage", "goes down", "going down", "keeps going", "keeps dropping", "keeps disconnecting", "disconnect", "drops", "unreliable", "not stable",
                  "unstable", "नेट बंद", "नेट चला जाता", "बार बार बंद", "net band", "net chala"]
SLOW_WORDS = ["slow", "buffering", "laggy", "lagging", "speed is low", "low speed", "speed nahi", "धीमा", "dheema", "dheemi"]  # not bare "lag"/"speed": "lag sakta hai" means "can be installed"
SUPPORT_WORDS = ["no support", "support", "nobody helps", "complaint", "no one responds", "service is bad", "no response"]
PRICE_WORDS = ["cheap", "cheaper", "cheapest", "lowest cost", "lowest price", "lower cost", "reduce cost", "less expensive", "too expensive", "reduce the price", "afford",
               "low cost", "tight budget", "budget friendly", "sasta", "सस्ता", "कम खर्च"]
RELIABLE_WORDS = ["reliable", "uptime", "never go down", "mission critical", "भरोसेमंद"]
NOTHING_WORDS = ["nothing", "nothing else", "no thanks", "no thank you", "that's all", "thats all", "that is all", "none", "no need", "nope", "nahi", "nahin", "नहीं", "कुछ नहीं",
                 "bas itna", "bas", "no", "na", "nah", "not needed", "don't need", "dont need", "do not need"]
YES_WORDS = ["yes", "yeah", "yep", "yup", "yea", "sure", "ok", "okay", "of course", "haan", "han", "haa", "ji", "ji haan", "हाँ", "हां", "जी", "हा", "available", "hai", "है", "correct", "right"]
UNSURE_WORDS = ["not sure", "unsure", "don't know", "dont know", "do not know", "no idea", "maybe", "pata nahi", "पता नहीं", "not certain", "can't say", "cant say"]
FLEXIBLE_WORDS = ["flexible", "no limit", "no budget", "not fixed", "depends", "whatever", "any budget", "budget is not a problem", "no constraint"]
RECOMMEND_WORDS = ["recommend", "recommendation", "suggest", "show me", "what do you recommend", "bundle", "quote", "सुझाव", "बताओ", "बताइए", "dikhao", "dikha do", "go ahead",
                   "that is enough", "enough questions", "just show"]
NEGATORS = ["no", "not", "dont", "don't", "do not", "without", "skip", "never", "nahi", "nahin", "नहीं", "बिना", "mat", "remove", "drop"]
NEG_NEUTRAL = re.compile(r"\b(?:no problem|no worries|not sure|no idea|not bad|no issue)\b")

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
                "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
                "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10}
NUMBER_PATTERNS = {
    "cameras": r"(\d+)\s*(?:cctv|cameras?|camere|kamere|कैमरे?)",
    "mobile_lines": r"(\d+)\s*(?:sims?|lines?|mobile numbers?|phone numbers?|connections?)",
    "pos_counters": r"(\d+)\s*(?:counters?|pos|billing)",
    "vehicles": r"(\d+)\s*(?:vehicles?|trucks?|vans?|cars?|bikes?|गाड़ी|वाहन)",
    "machines": r"(\d+)\s*(?:machines?|devices?|sensors?)",
}

# ---------------------------------------------------------------- the discovery plan
# Topics, in the order they usually matter. Each is asked at most once, only when relevant, and never if the customer already covered it.
CHANNEL_TAGS = {"whatsapp", "sms", "pos", "phone_system", "toll_free"}
OFFICE_TAGS = {"email", "backup", "security", "firewall", "website"}
PHYSICAL_TAGS = {"cctv", "iot", "fleet"}
TOPIC_TAGS = {"channels": CHANNEL_TAGS, "office": OFFICE_TAGS, "physical": PHYSICAL_TAGS}
QUESTIONS = ["pain", "connectivity", "channels", "office", "physical", "cameras", "pos", "machines", "vehicles", "budget"]
FOLLOW_UPS = {"cameras": ("cctv", "cameras"), "pos": ("pos", "pos_counters"), "machines": ("iot", "machines"), "vehicles": ("fleet", "vehicles")}
MAX_QUESTIONS = 5
FOLLOW_UNITS = {"cameras": r"cameras?|cctv|camere|kamere", "pos": r"counters?|pos|tablets?|billing", "machines": r"machines?|devices?|sensors?", "vehicles": r"vehicles?|trucks?|vans?|cars?|bikes?"}


def _has(text: str, words: list[str]) -> bool:
    return _find(text, words) is not None


def _find(text: str, words: list[str]) -> int | None:
    """Index of the first occurrence of any word (whole-word for Latin text)."""
    best = None
    for w in words:
        if w.isascii():
            m = re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text)
            idx = m.start() if m else -1
        else:
            idx = text.find(w)
        if idx >= 0 and (best is None or idx < best):
            best = idx
    return best


def _negated(text: str, pos: int) -> bool:
    """Is the thing at `pos` negated within its own clause ("no cctv", "don't need sms", "cctv nahi chahiye")?"""
    before = re.split(r"[,;.?!]|\bbut\b|\blekin\b|\bpar\b", text[:pos])[-1]
    tokens = before.split()[-4:]
    if any(t.strip("'\"") in NEGATORS for t in tokens) or any(a + " " + b in ("do not", "no need") for a, b in zip(tokens, tokens[1:])):
        return True
    after = text[pos:pos + 60].split()[1:4]  # "cctv nahi chahiye"
    return any(t in ("nahi", "nahin", "नहीं", "mat") for t in after)


def _normalise(text: str) -> str:
    t = (text or "").lower().strip()
    t = NEG_NEUTRAL.sub(" ", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), t)  # 5k -> 5000
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)s?\b", lambda m: str(int(float(m.group(1)) * 100000)), t)
    for w, n in sorted(NUMBER_WORDS.items(), key=lambda kv: -len(kv[0])):  # "four cameras" -> "4 cameras", "चार कैमरे" -> "4 कैमरे"
        t = re.sub(r"(?<!\w)" + re.escape(w) + r"(?=\s+(?:cctv|cameras?|sims?|lines?|counters?|vehicles?|trucks?|machines?|devices?|कैमरे?|गाड़ी|वाहन))", str(n), t)
    return re.sub(r"\s+", " ", t)


# ---------------------------------------------------------------- reading a message
def extract_rules(text: str, last_question: str | None = None) -> dict:
    """Keyword/number extraction used by the offline provider and as a safety net for the LLM provider."""
    t = _normalise(text)
    out: dict = {}
    wants, rejects = [], []
    for tag, words in WANT_KEYWORDS.items():
        pos = _find(t, words)
        if pos is None:
            continue
        # "wifi for patients" is guest Wi-Fi, but a plain "wifi is slow" is a complaint, not a product request
        if tag == "guest_wifi" and _has(t, ["wifi is slow", "wi-fi is slow", "wifi slow", "wifi not working"]):
            continue
        (rejects if _negated(t, pos) else wants).append(tag)
    if wants:
        out["wants"] = wants
    if rejects:
        out["rejects"] = rejects

    for conn, words in CONNECTIVITY_WORDS.items():
        pos = _find(t, words)
        if pos is not None:
            if conn == "fibre" and _negated(t, pos):
                out["fibre_available"] = False
            else:
                out["connectivity"] = conn
            break

    for key, pat in NUMBER_PATTERNS.items():
        m = re.search(pat, t)
        if m and 0 < int(m.group(1)) <= 500:
            out[key] = int(m.group(1))
    if re.search(r"no\s+fib(?:re|er)|fib(?:re|er)\s+(?:is\s+)?(?:not|nahi)|not\s+(?:available|feasible)\s+(?:for\s+)?fib|wireless only|no broadband line|fibre nahi|फाइबर नहीं", t):
        out["fibre_available"] = False
        out.pop("connectivity", None) if out.get("connectivity") == "fibre" else None
    elif re.search(r"fib(?:re|er)\s+(?:is\s+)?available|have\s+fib(?:re|er)|fib(?:re|er)\s+hai|fibre installed|already have fibre", t):
        out["fibre_available"] = True

    about_net = re.sub(r"machine(?:s)?\s+(?:downtime|uptime|breakdowns?|stoppage)|downtime\s+of\s+(?:the\s+)?machines?", " ", t)  # the factory floor, not the internet
    if _has(about_net, DOWNTIME_WORDS):
        out["pain_downtime"] = True
    if _has(about_net, SLOW_WORDS) and "pain_downtime" not in out and not _has(about_net, ["wifi is slow"]):
        out["pain_slow"] = True
    if _has(t, PRICE_WORDS):
        out["priority"] = "price"
    elif _has(t, RELIABLE_WORDS):
        out["priority"] = "reliability"
    if re.search(r"only\s+(?:a\s+)?(?:mobile|sim)|just\s+(?:a\s+)?sim|sirf\s+sim", t):
        out["mobile_only"] = True

    budget = re.search(r"(?:budget|spend|pay|afford|under|within|upto|up to|around|about|max|maximum)[^0-9]{0,20}(?:₹|rs\.?|inr)?\s*([\d,]{3,7})|(?:₹|rs\.?|inr)\s*([\d,]{3,7})", t)
    if budget:
        val = int((budget.group(1) or budget.group(2)).replace(",", ""))
        if 200 <= val <= 1_000_000:
            out["monthly_budget"] = val
    if _has(t, FLEXIBLE_WORDS):
        out["budget_flexible"] = True

    # ---- short answers are read against the question that was just asked
    words = t.split()
    short = len(words) <= 5 and bool(last_question)
    bare_yes = short and _has(t, YES_WORDS) and not _has(t, NOTHING_WORDS) and not wants and not rejects and not out.get("connectivity")
    declines = short and bool(_has(t, NOTHING_WORDS)) and not wants and not rejects  # "no antivirus" rejects one thing; it is not a bare "no"
    if _has(t, UNSURE_WORDS) and last_question:
        out["_unsure"] = True
        declines = False
    if last_question == "connectivity":
        if bare_yes:
            out["fibre_available"] = True
        elif declines:
            out["fibre_available"] = False
    elif last_question in TOPIC_TAGS:
        if bare_yes:
            out["_clarify"] = last_question  # "yes" - to which of the options?
        elif declines or (rejects and not wants):
            out["_declined"] = last_question
    elif last_question in FOLLOW_UPS and re.fullmatch(r"[\s]*[\d,]+\s*(?:nos?|pieces?|" + FOLLOW_UNITS[last_question] + r")?[\s.]*", t):
        val = int(re.sub(r"\D", "", t))
        if 0 < val <= 500:
            out[FOLLOW_UPS[last_question][1]] = val
    elif last_question == "budget" and re.fullmatch(r"[\s₹rs.]*[\d,]+\s*(?:per month|a month|/month|monthly|pm)?", t):
        val = int(re.sub(r"\D", "", t))
        if val >= 200:
            out["monthly_budget"] = val
    elif last_question == "pain":
        if declines or _has(t, ["fine", "ok", "okay", "good", "no problem", "upgrade"]):
            out["_declined"] = "pain"
    if last_question not in FOLLOW_UPS and "monthly_budget" not in out and re.fullmatch(r"\s*(?:₹|rs\.?|inr)?\s*\d[\d,]{2,6}\s*(?:rs\.?|rupees|per month|a month|/month|monthly|pm)?\s*", t) and 500 <= int(re.sub(r"\D", "", t)) <= 1_000_000:
        out["monthly_budget"] = int(re.sub(r"\D", "", t))  # "5000" on its own, whatever was asked, is almost certainly the budget
    if last_question == "budget" and (declines or out.get("budget_flexible")):
        out["_declined"] = "budget"
    return {k: v for k, v in out.items() if v is not None}


def wants_recommendation(text: str) -> bool:
    t = (text or "").lower()
    return _has(t, RECOMMEND_WORDS) or "recommendation" in t or "सुझाव" in t


# ---------------------------------------------------------------- remembering it
def merge_needs(needs: dict, update: dict) -> dict:
    out = dict(needs)
    rejects = set(out.get("rejects", []))
    for k, v in (update or {}).items():
        if k.startswith("_"):
            continue  # reading hints, not facts
        if k == "wants":
            valid = {w for w in v if w in NEED_PRODUCTS}
            out["wants"] = sorted(set(out.get("wants", [])) | valid)
            rejects -= valid  # changed their mind
        elif k == "rejects":
            bad = {w for w in v if w in NEED_PRODUCTS}
            rejects |= bad
            out["wants"] = sorted(set(out.get("wants", [])) - bad)
        elif k in ("mobile_lines", "cameras", "pos_counters", "vehicles", "machines", "monthly_budget"):
            if isinstance(v, (int, float)) and v > 0:
                out[k] = int(v)
        elif k in ("fibre_available", "pain_downtime", "pain_slow", "mobile_only", "no_more_needs", "budget_flexible") and isinstance(v, bool):
            out[k] = v
        elif k == "priority" and v in ("price", "reliability"):
            out[k] = v
        elif k == "connectivity" and v in ("fibre", "5g", "leased_line"):
            out[k] = v
    if rejects:
        out["rejects"] = sorted(rejects)
    else:
        out.pop("rejects", None)  # they changed their mind about everything they had ruled out
    return out


def mark_declined(needs: dict, topic: str) -> dict:
    """The customer said 'nothing' / 'fine' to a topic: remember it so it is not asked about again and not guessed."""
    out = dict(needs)
    out["declined"] = sorted(set(out.get("declined", [])) | {topic})
    return out


# ---------------------------------------------------------------- the plan
def _segment_code(profile) -> str:
    from ..profile import SEGMENT_CODE

    return SEGMENT_CODE.get(getattr(profile, "segment", ""), "micro") if profile else "micro"


SEGMENT_ORDER = {
    "micro": ["pain", "connectivity", "channels", "physical", "budget"],                      # kirana, salon, pharmacy: UPI/POS, WhatsApp, a camera
    "prof": ["pain", "connectivity", "office", "channels", "physical", "budget"],            # clinic, CA firm: uptime, email, backup, security
    "multi": ["pain", "connectivity", "channels", "physical", "office", "budget"],           # chains: one bill, CCTV, failover
    "mfg": ["pain", "connectivity", "physical", "office", "budget"],                         # factories: machines, firewall; not WhatsApp marketing
}


def _relevant(topic: str, needs: dict, profile_has_budget: bool, seg: str, current: str) -> bool:
    wants, rejects = set(needs.get("wants", [])), set(needs.get("rejects", []))
    declined = set(needs.get("declined", []))
    if topic in declined:
        return False
    if topic == "pain":
        # a hotspot / no connection already tells us the pain; do not make them state the obvious
        return not (needs.get("pain_downtime") or needs.get("pain_slow") or needs.get("priority") or current in ("Mobile hotspot", "None"))
    if topic == "connectivity":
        return not (needs.get("connectivity") in ("5g", "leased_line") or needs.get("fibre_available") is not None or needs.get("mobile_only") or current == "Leased line")
    if topic in TOPIC_TAGS:
        tags = TOPIC_TAGS[topic]
        if wants & tags or tags <= rejects:
            return False  # already told us, or ruled the whole area out
        if topic == "office" and seg == "micro":
            return False  # price-sensitive small shops: do not interrogate about IT; the recommendation still includes the essentials
        return True
    if topic in FOLLOW_UPS:
        tag, key = FOLLOW_UPS[topic]
        return tag in wants and not needs.get(key)
    if topic == "budget":
        return not (needs.get("monthly_budget") or profile_has_budget or needs.get("budget_flexible"))
    return False


def next_question(needs: dict, profile_has_budget: bool, asked: list[str], profile=None, current_internet: str = "") -> str | None:
    """The next topic worth asking about, or None when we know enough. Follow-ups about quantities come first (they change the price)."""
    seg = _segment_code(profile)
    current = current_internet or (getattr(profile, "current_internet", "") if profile else "")
    for q in ["cameras", "pos", "machines", "vehicles"] + SEGMENT_ORDER.get(seg, SEGMENT_ORDER["micro"]):
        if q not in asked and _relevant(q, needs, profile_has_budget, seg, current):
            return q
    return None
