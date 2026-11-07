"""Deterministic reply text (English / Hindi). Used directly by the mock provider and as the factual base that the
LLM may rephrase. Every rupee amount shown comes from the quote engine.

English and Hindi are written by hand. The other eight languages (mr, kn, gu, te, ta, bn, pa, ml) are machine-translated into
data/advisor_i18n.json by scripts/translate_advisor.py and merged in at import. A missing translation falls back to English."""
import json
from pathlib import Path


class Loc(dict):
    """{lang: text-or-structure}; asking for a language that has no entry returns the English one."""

    def __missing__(self, lang):
        return self["en"]

QUESTIONS = Loc({
    "en": {
        "pain": "Today you use {current}. What troubles you most about it - slow speed, the internet going down, or no support when something breaks?",
        "connectivity": "Can a fibre broadband line be installed at your shop/office? If you are unsure, say 'not sure' and I will plan a wireless link as a backup.",
        "channels": "How do you reach and serve your customers - WhatsApp, SMS reminders, billing/POS counters, a toll-free or phone line? Say 'nothing' if none of these.",
        "office": "And for the office side - business email, backup of your data, antivirus/security, or a website? Say 'nothing' if none of these.",
        "physical": "Do you want CCTV for the premises - or machine monitoring or vehicle tracking? Say 'nothing' if none of these.",
        "cameras": "How many CCTV cameras do you want?",
        "pos": "How many billing counters / POS tablets do you need?",
        "machines": "How many machines should we monitor?",
        "vehicles": "How many vehicles do you want to track?",
        "budget": "Roughly what monthly budget would you be comfortable with (in rupees)? Say 'flexible' if you have no fixed limit.",
        "extras": "Besides internet and mobile lines, do you need anything for customers or the office - e.g. WhatsApp, SMS, business email, CCTV, billing/POS, backup or security? Say 'nothing else' if not.",
        "fibre": "Is a fibre broadband line available at your shop/office? If you are unsure, say 'not sure' and I will plan a wireless link as a fallback.",
        "lines": "How many business mobile lines (SIMs) do you need?",
    },
    "hi": {
        "pain": "अभी आप {current} इस्तेमाल करते हैं। इसमें सबसे बड़ी परेशानी क्या है - स्पीड धीमी, इंटरनेट बार-बार बंद होना, या दिक्कत आने पर सपोर्ट न मिलना?",
        "connectivity": "क्या आपकी दुकान/ऑफिस पर फाइबर ब्रॉडबैंड लाइन लग सकती है? पक्का न हो तो 'not sure' लिखें, मैं बैकअप के तौर पर वायरलेस लिंक रखूँगा।",
        "channels": "आप अपने ग्राहकों तक कैसे पहुँचते और उन्हें कैसे सेवा देते हैं - WhatsApp, SMS रिमाइंडर, बिलिंग/POS काउंटर, टोल-फ़्री या फ़ोन लाइन? इनमें से कुछ नहीं चाहिए तो 'nothing' लिखें।",
        "office": "और ऑफिस के लिए - बिज़नेस ईमेल, डेटा का बैकअप, एंटीवायरस/सिक्योरिटी या वेबसाइट? इनमें से कुछ नहीं चाहिए तो 'nothing' लिखें।",
        "physical": "क्या आपको परिसर के लिए CCTV चाहिए - या मशीन मॉनिटरिंग या गाड़ियों की ट्रैकिंग? इनमें से कुछ नहीं चाहिए तो 'nothing' लिखें।",
        "cameras": "आप कितने CCTV कैमरे लगवाना चाहते हैं?",
        "pos": "कितने बिलिंग काउंटर / POS टैबलेट चाहिए?",
        "machines": "कितनी मशीनों की निगरानी करनी है?",
        "vehicles": "कितनी गाड़ियों को ट्रैक करना है?",
        "budget": "आप हर महीने लगभग कितना बजट रखना चाहेंगे (रुपये में)? कोई तय सीमा नहीं है तो 'flexible' लिखें।",
        "extras": "इंटरनेट और मोबाइल लाइन के अलावा क्या आपको ग्राहकों या ऑफिस के लिए कुछ और चाहिए - जैसे WhatsApp, SMS, बिज़नेस ईमेल, CCTV, बिलिंग/POS, बैकअप या सिक्योरिटी? नहीं चाहिए तो 'nothing else' लिखें।",
        "fibre": "क्या आपकी दुकान/ऑफिस पर फाइबर ब्रॉडबैंड लाइन उपलब्ध है? पक्का न हो तो 'not sure' लिखें, मैं वायरलेस विकल्प रखूँगा।",
        "lines": "आपको कितनी बिज़नेस मोबाइल लाइन (SIM) चाहिए?",
    },
})
CHIPS = Loc({
    "en": {
        "pain": ["Internet keeps going down", "It is slow", "No proper support", "Mostly fine, want an upgrade"],
        "connectivity": ["Yes, fibre is available", "No fibre here", "Not sure"],
        "channels": ["WhatsApp", "SMS reminders", "Billing / POS", "Phone line / toll-free", "Nothing"],
        "office": ["Business email", "Cloud backup", "Antivirus / security", "Website", "Nothing"],
        "physical": ["CCTV cameras", "Machine monitoring", "Vehicle tracking", "Nothing"],
        "cameras": ["2", "4", "8"],
        "pos": ["1", "2", "4"],
        "machines": ["2", "5", "10"],
        "vehicles": ["2", "5", "10"],
        "budget": ["2500", "5000", "10000", "Flexible"],
        "extras": ["WhatsApp + SMS", "CCTV", "Billing / POS", "Email + security", "Nothing else"],
        "fibre": ["Yes, fibre is available", "No fibre here", "Not sure"],
        "lines": ["1", "2", "4", "6"],
    },
    "hi": {
        "pain": ["इंटरनेट बार-बार बंद होता है", "स्पीड धीमी है", "सपोर्ट नहीं मिलता", "ठीक है, अपग्रेड चाहिए"],
        "connectivity": ["हाँ, फाइबर है", "फाइबर नहीं है", "not sure"],
        "channels": ["WhatsApp", "SMS रिमाइंडर", "बिलिंग / POS", "फ़ोन लाइन / टोल-फ़्री", "nothing"],
        "office": ["बिज़नेस ईमेल", "क्लाउड बैकअप", "एंटीवायरस / सिक्योरिटी", "वेबसाइट", "nothing"],
        "physical": ["CCTV कैमरे", "मशीन मॉनिटरिंग", "गाड़ी ट्रैकिंग", "nothing"],
        "cameras": ["2", "4", "8"],
        "pos": ["1", "2", "4"],
        "machines": ["2", "5", "10"],
        "vehicles": ["2", "5", "10"],
        "budget": ["2500", "5000", "10000", "flexible"],
        "extras": ["WhatsApp + SMS", "CCTV", "बिलिंग / POS", "ईमेल + सिक्योरिटी", "nothing else"],
        "fibre": ["हाँ, फाइबर है", "फाइबर नहीं है", "not sure"],
        "lines": ["1", "2", "4", "6"],
    },
})

CLARIFY = Loc({
    "en": {
        "channels": "Which ones - WhatsApp, SMS, billing/POS, or a phone line?",
        "office": "Which ones - business email, backup, security or a website?",
        "physical": "Which one - CCTV cameras, machine monitoring or vehicle tracking?",
    },
    "hi": {
        "channels": "कौन-से - WhatsApp, SMS, बिलिंग/POS या फ़ोन लाइन?",
        "office": "कौन-से - बिज़नेस ईमेल, बैकअप, सिक्योरिटी या वेबसाइट?",
        "physical": "कौन-सा - CCTV कैमरे, मशीन मॉनिटरिंग या गाड़ी ट्रैकिंग?",
    },
})

GREETING = Loc({
    "en": "Hello{name}! I am your Accel Business advisor. I can see you run {biz} in {city} with {emp} people across {sites} site(s). I'll ask a few short questions, only about what matters for you, and then recommend a bundle with a clear monthly price.",
    "hi": "नमस्ते{name}! मैं आपका Accel Business सलाहकार हूँ। मैं देख रहा हूँ कि आप {city} में {biz} चलाते हैं, {emp} लोग और {sites} साइट। कुछ छोटे सवाल पूछकर मैं आपके लिए साफ़ मासिक कीमत वाला बंडल सुझाऊँगा।",
})
ACK = Loc({
    "en": {"wants": "Noted - I'll look at {items}.", "fibre_no": "Understood, I will plan for sites without fibre.", "downtime": "Got it - reliability matters to you.", "price": "Understood - I'll keep the cost tight."},
    "hi": {"wants": "ठीक है - मैं {items} देखूँगा।", "fibre_no": "समझ गया, बिना फाइबर वाली साइट के लिए योजना बनाऊँगा।", "downtime": "समझ गया - आपके लिए भरोसेमंद नेट ज़रूरी है।", "price": "समझ गया - मैं खर्च कम रखूँगा।"},
})
REC_HEAD = Loc({
    "en": "Based on what you told me, here is my recommended **{tier}** bundle:",
    "hi": "आपकी बातों के आधार पर मेरा सुझाया हुआ **{tier}** बंडल:",
})
TIER_NAMES = Loc({"en": {"starter": "Starter", "recommended": "Recommended", "complete": "Complete"},
              "hi": {"starter": "स्टार्टर", "recommended": "रिकमेंडेड", "complete": "कंप्लीट"}})
REC_TOTAL = Loc({
    "en": "**Total: ₹{monthly} per month** (incl. {gst}% GST) plus **₹{setup} one-time setup** (incl. GST), on a {term}-month contract. First payment: ₹{first}.",
    "hi": "**कुल: ₹{monthly} प्रति माह** ({gst}% GST सहित) और **₹{setup} एकमुश्त सेटअप** (GST सहित), {term} महीने के कॉन्ट्रैक्ट पर। पहला भुगतान: ₹{first}।",
})
BUDGET_OK = Loc({"en": "That fits within your ₹{budget} monthly budget.", "hi": "यह आपके ₹{budget} मासिक बजट में आता है।"})
BUDGET_OVER = Loc({"en": "This is above your ₹{budget} monthly budget, so I trimmed to the essentials - you can still add items below.", "hi": "यह आपके ₹{budget} मासिक बजट से ज़्यादा है, इसलिए मैंने ज़रूरी चीज़ें ही रखी हैं - नीचे से और जोड़ सकते हैं।"})
EXCLUDED = Loc({"en": "Not available for you right now: {items}.", "hi": "अभी आपके लिए उपलब्ध नहीं: {items}।"})
SAVINGS = Loc({"en": "Compared with your current telecom spend of ₹{cur}, this is ₹{diff} {dir} per month before GST.", "hi": "आपके मौजूदा टेलीकॉम खर्च ₹{cur} की तुलना में यह GST से पहले हर महीने ₹{diff} {dir} है।"})
NEXT_STEP = Loc({"en": "Open the bundle to toggle anything optional, then continue to the quote and checkout.", "hi": "बंडल खोलकर वैकल्पिक चीज़ें चुनें/हटाएँ, फिर कोटेशन और चेकआउट पर जाएँ।"})
FALLBACK_HELP = Loc({
    "en": "I didn't catch a specific need in that - you can tell me things like '4 cameras', 'WhatsApp for customers' or 'internet keeps dropping'. Or say 'recommend' and I'll suggest a bundle now.",
    "hi": "मुझे इसमें कोई ख़ास ज़रूरत समझ नहीं आई - आप '4 कैमरे', 'ग्राहकों के लिए WhatsApp' या 'इंटरनेट बार-बार बंद' जैसा कुछ लिख सकते हैं। या 'recommend' लिखें, मैं अभी बंडल सुझा दूँगा।",
})
CHEAPER = Loc({"en": "I've re-planned with cost as the priority.", "hi": "मैंने खर्च को प्राथमिकता देकर दोबारा योजना बनाई है।"})


def _merge_generated() -> None:
    f = Path(__file__).resolve().parents[2] / "data" / "advisor_i18n.json"
    if not f.exists():
        return
    g = globals()
    for lang, names in json.loads(f.read_text(encoding="utf-8")).items():
        for name, value in names.items():
            if name in g and isinstance(g[name], Loc) and not (lang == "hi" and "hi" in g[name]):  # never override hand-written Hindi
                en = g[name].get("en")
                g[name][lang] = {**en, **value} if isinstance(en, dict) and isinstance(value, dict) else value  # a question added later falls back to English per key


def chips_for(lang: str, question: str) -> list[str]:
    """Quick-reply chips. Only English and Hindi chips exist, because the rules engine only understands those words
    when a chip is tapped; the browser shows other languages' labels itself and still sends the original text."""
    return CHIPS["hi" if lang == "hi" else "en"].get(question, [])


_merge_generated()
