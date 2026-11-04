"""Deterministic reply text (English / Hindi). Used directly by the mock provider and as the factual base that the
LLM may rephrase. Every rupee amount shown comes from the quote engine."""

QUESTIONS = {
    "en": {
        "pain": "What is the biggest connectivity headache today - slow speed, internet going down, or no support when something breaks?",
        "extras": "Besides internet and mobile lines, do you need anything for customers or the office - e.g. WhatsApp, SMS, business email, CCTV, billing/POS, backup or security? Say 'nothing else' if not.",
        "fibre": "Is a fibre broadband line available at your shop/office? If you are unsure, say 'not sure' and I will plan a wireless link as a fallback.",
        "lines": "How many business mobile lines (SIMs) do you need?",
        "cameras": "How many CCTV cameras do you want?",
        "pos": "How many billing counters / POS tablets do you need?",
        "budget": "Roughly what monthly budget would you be comfortable with (in rupees)?",
    },
    "hi": {
        "pain": "अभी कनेक्टिविटी की सबसे बड़ी परेशानी क्या है - स्पीड धीमी, इंटरनेट बार-बार बंद होना, या दिक्कत आने पर सपोर्ट न मिलना?",
        "extras": "इंटरनेट और मोबाइल लाइन के अलावा क्या आपको ग्राहकों या ऑफिस के लिए कुछ और चाहिए - जैसे WhatsApp, SMS, बिज़नेस ईमेल, CCTV, बिलिंग/POS, बैकअप या सिक्योरिटी? नहीं चाहिए तो 'nothing else' लिखें।",
        "fibre": "क्या आपकी दुकान/ऑफिस पर फाइबर ब्रॉडबैंड लाइन उपलब्ध है? पक्का न हो तो 'not sure' लिखें, मैं वायरलेस विकल्प रखूँगा।",
        "lines": "आपको कितनी बिज़नेस मोबाइल लाइन (SIM) चाहिए?",
        "cameras": "आप कितने CCTV कैमरे लगवाना चाहते हैं?",
        "pos": "कितने बिलिंग काउंटर / POS टैबलेट चाहिए?",
        "budget": "आप हर महीने लगभग कितना बजट रखना चाहेंगे (रुपये में)?",
    },
}
CHIPS = {
    "en": {
        "pain": ["Internet keeps going down", "It is slow", "No proper support", "Mostly fine, want an upgrade"],
        "extras": ["WhatsApp + SMS", "CCTV", "Billing / POS", "Email + security", "Nothing else"],
        "fibre": ["Yes, fibre is available", "No fibre here", "Not sure"],
        "lines": ["1", "2", "4", "6"],
        "cameras": ["2", "4", "8"],
        "pos": ["1", "2", "4"],
        "budget": ["2500", "5000", "10000"],
    },
    "hi": {
        "pain": ["इंटरनेट बार-बार बंद होता है", "स्पीड धीमी है", "सपोर्ट नहीं मिलता", "ठीक है, अपग्रेड चाहिए"],
        "extras": ["WhatsApp + SMS", "CCTV", "बिलिंग / POS", "ईमेल + सिक्योरिटी", "nothing else"],
        "fibre": ["हाँ, फाइबर है", "फाइबर नहीं है", "not sure"],
        "lines": ["1", "2", "4", "6"],
        "cameras": ["2", "4", "8"],
        "pos": ["1", "2", "4"],
        "budget": ["2500", "5000", "10000"],
    },
}

GREETING = {
    "en": "Hello{name}! I am your Accel Business advisor. I can see you run {biz} in {city} with {emp} people across {sites} site(s). I'll ask a few quick questions and then recommend a bundle with a clear monthly price.",
    "hi": "नमस्ते{name}! मैं आपका Accel Business सलाहकार हूँ। मैं देख रहा हूँ कि आप {city} में {biz} चलाते हैं, {emp} लोग और {sites} साइट। कुछ छोटे सवाल पूछकर मैं आपके लिए साफ़ मासिक कीमत वाला बंडल सुझाऊँगा।",
}
ACK = {
    "en": {"wants": "Noted - I'll look at {items}.", "fibre_no": "Understood, I will plan for sites without fibre.", "downtime": "Got it - reliability matters to you.", "price": "Understood - I'll keep the cost tight."},
    "hi": {"wants": "ठीक है - मैं {items} देखूँगा।", "fibre_no": "समझ गया, बिना फाइबर वाली साइट के लिए योजना बनाऊँगा।", "downtime": "समझ गया - आपके लिए भरोसेमंद नेट ज़रूरी है।", "price": "समझ गया - मैं खर्च कम रखूँगा।"},
}
REC_HEAD = {
    "en": "Based on what you told me, here is my recommended **{tier}** bundle:",
    "hi": "आपकी बातों के आधार पर मेरा सुझाया हुआ **{tier}** बंडल:",
}
TIER_NAMES = {"en": {"starter": "Starter", "recommended": "Recommended", "complete": "Complete"},
              "hi": {"starter": "स्टार्टर", "recommended": "रिकमेंडेड", "complete": "कंप्लीट"}}
REC_TOTAL = {
    "en": "**Total: ₹{monthly} per month** (incl. {gst}% GST) plus **₹{setup} one-time setup** (incl. GST), on a {term}-month contract. First payment: ₹{first}.",
    "hi": "**कुल: ₹{monthly} प्रति माह** ({gst}% GST सहित) और **₹{setup} एकमुश्त सेटअप** (GST सहित), {term} महीने के कॉन्ट्रैक्ट पर। पहला भुगतान: ₹{first}।",
}
BUDGET_OK = {"en": "That fits within your ₹{budget} monthly budget.", "hi": "यह आपके ₹{budget} मासिक बजट में आता है।"}
BUDGET_OVER = {"en": "This is above your ₹{budget} monthly budget, so I trimmed to the essentials - you can still add items below.", "hi": "यह आपके ₹{budget} मासिक बजट से ज़्यादा है, इसलिए मैंने ज़रूरी चीज़ें ही रखी हैं - नीचे से और जोड़ सकते हैं।"}
EXCLUDED = {"en": "Not available for you right now: {items}.", "hi": "अभी आपके लिए उपलब्ध नहीं: {items}।"}
SAVINGS = {"en": "Compared with your current telecom spend of ₹{cur}, this is ₹{diff} {dir} per month before GST.", "hi": "आपके मौजूदा टेलीकॉम खर्च ₹{cur} की तुलना में यह GST से पहले हर महीने ₹{diff} {dir} है।"}
NEXT_STEP = {"en": "Open the bundle to toggle anything optional, then continue to the quote and checkout.", "hi": "बंडल खोलकर वैकल्पिक चीज़ें चुनें/हटाएँ, फिर कोटेशन और चेकआउट पर जाएँ।"}
FALLBACK_HELP = {
    "en": "I didn't catch a specific need in that - you can tell me things like '4 cameras', 'WhatsApp for customers' or 'internet keeps dropping'. Or say 'recommend' and I'll suggest a bundle now.",
    "hi": "मुझे इसमें कोई ख़ास ज़रूरत समझ नहीं आई - आप '4 कैमरे', 'ग्राहकों के लिए WhatsApp' या 'इंटरनेट बार-बार बंद' जैसा कुछ लिख सकते हैं। या 'recommend' लिखें, मैं अभी बंडल सुझा दूँगा।",
}
CHEAPER = {"en": "I've re-planned with cost as the priority.", "hi": "मैंने खर्च को प्राथमिकता देकर दोबारा योजना बनाई है।"}
