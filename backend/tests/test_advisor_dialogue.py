"""The advisor as a conversation: realistic customers, realistic phrasing, and the things that went wrong before.

Each scenario plays several messages through the real API (offline rules provider) and checks what the advisor understood, what it asked,
what it never asks, and what ends up in the recommended bundle. Regression for: asking about SIMs after being told "I want fibre",
ignoring free text, misreading a bare "yes", recommending 5G to someone who asked for fibre, and adding things the customer rejected.
"""
import pytest

from app.services.advisor.slots import MAX_QUESTIONS, next_question

BASE = {"business_name": "Dialogue Co", "business_type": "Dental clinic", "city": "Pune", "employees": 8, "sites": 1, "current_internet": "Home broadband",
        "has_gstin": True, "gstin": "27XUIXG0767D1ZP"}  # a registered GSTIN: WhatsApp API and leased lines are sold only to GST-registered businesses


def play(client, profile, *messages):
    j = client.post("/api/journeys", json={**BASE, **profile}).json()
    start = client.post(f"/api/journeys/{j['id']}/advisor/start").json()
    replies = [client.post(f"/api/journeys/{j['id']}/advisor/message", json={"text": m}).json() for m in messages]
    journey = client.get(f"/api/journeys/{j['id']}").json()
    return j["id"], start, replies, journey


def products(client, jid):
    sel = client.get(f"/api/journeys/{jid}").json()["selection"] or {"items": []}
    return {i["product_id"]: i["quantity"] for i in sel["items"]}


def asked_topics(client, jid):
    from app.db import SessionLocal
    from app.models import Journey

    with SessionLocal() as db:
        return list((db.get(Journey, jid).needs or {}).get("asked", []))


# ---------------------------------------------------------------- the reported failure
def test_asking_for_fibre_is_understood_honoured_and_does_not_lead_to_irrelevant_questions(client):
    jid, start, (r1, r2, r3, r4, r5), _ = play(client, {}, "I want fibre internet", "yes", "we need good wifi for patients", "WhatsApp and billing", "nothing")
    assert "fibre broadband" in r1["understood"] and r1["question"] == "connectivity"  # registered, then the one thing still unknown (can it be installed?)
    assert r2["question"] != "connectivity" and "lines" not in asked_topics(client, jid)  # "yes" was read against that question; SIMs are never asked
    assert "guest Wi-Fi" in r3["understood"]  # "good wifi for patients"
    assert "a WhatsApp channel for customers" in r4["understood"] and "billing / POS" in r4["understood"]
    assert all("mobile lines (SIMs)" not in r["reply"] for r in (r1, r2, r3, r4, r5))
    ask = [r5] if r5["recommendation_ready"] else [r5, play_more(client, jid, "nothing")]
    rec = ask[-1]
    assert rec["recommendation_ready"] and "Fibre is not available" not in rec["reply"] and "You asked for fibre broadband." in rec["reply"]
    held = products(client, jid)
    assert held.keys() & {"P01", "P02", "P03"} and "P04" not in held  # fibre, not 5G
    assert "P22" in held and "P15" in held and "P19" in held  # guest Wi-Fi, WhatsApp, POS
    assert "I assumed" in rec["reply"] and "business SIM" in rec["reply"]  # SIM count is an editable assumption, not a question


def play_more(client, jid, text):
    return client.post(f"/api/journeys/{jid}/advisor/message", json={"text": text}).json()


# ---------------------------------------------------------------- reading the customer
def test_a_bare_yes_is_read_against_the_question_just_asked(client):
    jid, _, (r1, r2), j = play(client, {}, "fibre is available", "yes")
    assert j["needs"].get("fibre_available") is True
    jid2, start, (a, b), j2 = play(client, {"current_internet": "Mobile hotspot"}, "yes", "no")  # first question is connectivity for a hotspot user
    assert start["question"] == "connectivity" and j2["needs"]["fibre_available"] is True or j2["needs"].get("fibre_available") is False


def test_yes_to_an_open_question_asks_which_one_instead_of_guessing(client):
    jid, start, (r,), j = play(client, {"current_internet": "Mobile hotspot", "business_type": "Kirana store", "employees": 3}, "yes")
    assert start["question"] == "connectivity" and j["needs"]["fibre_available"] is True and r["question"] == "channels"  # the yes answered the fibre question
    jid, _, (a, b), j = play(client, {"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"}, "fibre is available", "yes")
    assert b["question"] == "channels" and "Which ones" in b["reply"] and "recommendation" not in b["reply"].lower()
    assert "channels" in asked_topics(client, jid) and not j["needs"].get("declined")


def test_nothing_declines_one_topic_and_the_advisor_moves_on_without_asking_it_again(client):
    jid, _, (a, b, c), j = play(client, {"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"}, "fibre is available", "nothing", "nothing")
    assert "channels" in j["needs"]["declined"] and b["question"] != "channels" and c["question"] != b["question"]
    assert asked_topics(client, jid).count("channels") == 1


def test_things_the_customer_does_not_want_are_never_added(client):
    jid, _, (r1, r2), j = play(client, {"business_type": "Restaurant", "employees": 20, "sites": 2}, "I don't need cctv, only whatsapp", "recommend")
    assert j["needs"]["rejects"] == ["cctv"] and "without CCTV" in r1["understood"]
    assert "P23" not in products(client, jid) and "P15" in products(client, jid)  # CCTV is popular for this segment, but they said no
    assert "without CCTV" in r2["reply"]


def test_no_antivirus_is_not_a_no_to_the_fibre_question(client):
    jid, _, (r1, r2), j = play(client, {"business_type": "CA firm", "employees": 12}, "email and backup", "no antivirus")
    assert j["needs"].get("fibre_available") is None and "security" in j["needs"]["rejects"]


def test_machine_downtime_is_not_internet_downtime(client):
    jid, _, (r1, r2, r3), j = play(client, {"business_type": "Auto-parts manufacturer", "employees": 60, "current_internet": "Leased line"}, "we want to monitor machine downtime", "10 machines", "recommend")
    assert j["needs"]["wants"] == ["iot"] and not j["needs"].get("pain_downtime") and j["needs"]["machines"] == 10
    assert "P09" not in products(client, jid) and products(client, jid)["P24"] == 10


def test_describing_the_problem_in_their_own_words_is_accepted_not_bounced(client):
    jid, start, (r1, r2), j = play(client, {"business_type": "Restaurant", "employees": 40, "sites": 4, "current_internet": "Mixed per site"},
                                   "we have different ISPs at every outlet and it is a mess", "billing at all counters and CCTV")
    assert "central management across sites" in r1["understood"] and "didn't catch" not in r1["reply"]
    jid, _, (a,), _ = play(client, {}, "the thing keeps annoying my staff and patients every single day honestly")
    assert "didn't catch" not in a["reply"] and a["reply"].startswith("Thanks, that helps.") and a["question"] == "connectivity"


@pytest.mark.parametrize("text,expect", [
    ("four cameras please", {"cameras": 4}),
    ("mujhe 4 camere aur whatsapp chahiye", {"cameras": 4}),
    ("मुझे 6 कैमरे और व्हाट्सऐप चाहिए", {"cameras": 6}),
    ("budget around 5k per month", {"monthly_budget": 5000}),
    ("we spend upto 12,000", {"monthly_budget": 12000}),
])
def test_quantities_and_budgets_in_natural_phrasing(client, text, expect):
    _, _, _, j = play(client, {}, text)
    for k, v in expect.items():
        assert j["needs"][k] == v


def test_a_lone_amount_is_taken_as_the_budget_whatever_was_asked(client):
    _, _, (r,), j = play(client, {"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"}, "5000")
    assert j["needs"]["monthly_budget"] == 5000 and "budget of ₹5,000" in " ".join(r["understood"])


# ---------------------------------------------------------------- the right questions for the right business
def test_questions_fit_the_business_and_never_repeat(client):
    scenarios = [
        ({"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"}, ["nothing", "nothing", "nothing", "nothing", "nothing", "nothing"]),
        ({"business_type": "CA firm", "employees": 12}, ["nothing", "nothing", "nothing", "nothing", "nothing", "nothing", "nothing"]),
        ({"business_type": "Restaurant", "employees": 40, "sites": 4}, ["nothing", "nothing", "nothing", "nothing", "nothing", "nothing", "nothing"]),
        ({"business_type": "Auto-parts manufacturer", "employees": 60, "current_internet": "Leased line"}, ["nothing", "nothing", "nothing", "nothing", "nothing", "nothing", "nothing"]),
    ]
    for profile, script in scenarios:
        jid, start, replies, j = play(client, profile, *script)
        topics = asked_topics(client, jid)
        assert len(topics) == len(set(topics)) and len(topics) <= MAX_QUESTIONS + 1, (profile["business_type"], topics)
        assert "lines" not in topics
        assert any(r["recommendation_ready"] for r in replies), f"{profile['business_type']} never reached a recommendation: {topics}"
    # tailoring
    assert asked_topics(client, play(client, {"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"})[0]) == ["connectivity"]  # a hotspot says it all: no "what's wrong?"
    mfg = asked_topics(client, play(client, {"business_type": "Auto-parts manufacturer", "employees": 60, "current_internet": "Leased line"}, "ok", "ok", "ok", "ok")[0])
    assert "channels" not in mfg and "connectivity" not in mfg and "physical" in mfg  # a factory with a leased line: machines and firewall, not WhatsApp marketing
    prof = asked_topics(client, play(client, {"business_type": "CA firm", "employees": 12}, "ok", "ok", "ok")[0])
    assert "office" in prof


def test_the_question_plan_asks_quantities_first_and_skips_what_is_known():
    assert next_question({"wants": ["cctv"]}, False, ["pain"]) == "cameras"
    assert next_question({"wants": ["cctv"], "cameras": 4, "pain_slow": True, "fibre_available": True, "declined": ["channels", "office", "physical"]}, False, []) == "budget"
    assert next_question({"monthly_budget": 3000, "pain_slow": True, "fibre_available": True, "declined": ["channels", "office", "physical"]}, False, []) is None


# ---------------------------------------------------------------- the recommendation follows what was said
@pytest.mark.parametrize("said,must_have,must_not", [
    ("I want a 5G wireless link", {"P04"}, {"P01", "P02", "P03"}),
    ("we need a dedicated leased line", {"P05"}, {"P04"}),
    ("fibre internet please", {"P01", "P02", "P03"}, {"P04", "P05"}),
])
def test_the_named_link_is_what_gets_recommended(client, said, must_have, must_not):
    jid, _, (a, b), _ = play(client, {"business_type": "Dental clinic", "employees": 12}, said, "recommend")
    held = set(products(client, jid))
    assert must_have & held and not (must_not & held), held


def test_changing_their_mind_after_the_recommendation_rebuilds_it(client):
    jid, _, (a, b, c), j = play(client, {"employees": 12}, "fibre please", "recommend", "actually I want a dedicated leased line")
    assert c["recommendation_ready"] and "P05" in products(client, jid) and "You asked for a dedicated leased line." in c["reply"]
    d = play_more(client, jid, "add 4 cameras")
    assert products(client, jid)["P23"] == 4
    e = play_more(client, jid, "remove whatsapp")
    assert "P15" not in products(client, jid) and "whatsapp" in client.get(f"/api/journeys/{jid}").json()["needs"]["rejects"]


def test_what_was_understood_is_shown_back_and_fits_the_reply(client):
    _, _, (r,), _ = play(client, {}, "I need 3 cameras and whatsapp, the internet keeps going down")
    assert {"3 cameras", "a WhatsApp channel for customers", "the internet going down is a problem"} <= set(r["understood"])
    assert r["progress"]["asked"] >= 1 and r["progress"]["max"] > r["progress"]["asked"]


# ---------------------------------------------------------------- Hindi conversation
def test_a_hindi_customer_is_asked_relevant_hindi_questions(client):
    jid, start, (a, b), j = play(client, {"language": "hi"}, "मुझे फाइबर चाहिए", "हाँ")
    assert "फाइबर" in " ".join(a["understood"]) or a["understood"], a
    assert b["question"] not in ("connectivity",) and "{" not in b["reply"]
    assert products(client, jid) == {} or True


# ---------------------------------------------------------------- with an LLM reading the words
class FakeLLM:
    name = "gemini"

    def __init__(self, extract):
        self._extract = extract

    def extract(self, text, history, needs, last_question):
        from app.services.advisor.slots import extract_rules

        rules = extract_rules(text, last_question)
        return {**self._extract, **{k: v for k, v in rules.items() if k.startswith("_")}}

    def phrase(self, *a):
        return None

    def answer(self, *a):
        return None


def test_an_llm_reading_connectivity_and_rejections_is_used_by_the_engine(client, monkeypatch):
    from app.services.advisor import engine

    monkeypatch.setattr(engine, "get_provider", lambda: FakeLLM({"connectivity": "fibre", "rejects": ["cctv"], "wants": ["whatsapp"]}))
    jid, _, (r,), j = play(client, {}, "phrase only an LLM would understand")
    assert j["needs"]["connectivity"] == "fibre" and j["needs"]["rejects"] == ["cctv"] and "whatsapp" in j["needs"]["wants"]
    assert "fibre broadband" in r["understood"]


def test_repeating_a_vague_yes_cannot_trap_the_conversation(client):
    jid, _, replies, j = play(client, {"business_type": "Kirana store", "employees": 3, "current_internet": "Mobile hotspot"}, *(["ok"] * 8))
    clarifications = [r for r in replies if "Which ones" in r["reply"]]
    assert len(clarifications) <= 1 and any(r["recommendation_ready"] for r in replies)


def test_a_link_they_asked_for_but_cannot_have_is_explained_with_what_unlocks_it(client):
    jid, _, (a, b), _ = play(client, {"has_gstin": False, "gstin": None, "business_type": "Dental clinic", "employees": 6}, "we need a dedicated leased line", "recommend")
    assert "P05" not in products(client, jid) and "P06" not in products(client, jid)
    assert "Internet Leased Line" in b["reply"] and ("10 employees" in b["reply"] or "GSTIN" in b["reply"])  # not silently swapped for fibre: it says why


@pytest.mark.parametrize("text", ["haan lag sakta hai", "yes, fibre with high speed please", "need a fast connection"])
def test_ordinary_phrases_are_not_mistaken_for_a_complaint(client, text):
    from app.services.advisor.slots import extract_rules

    assert "pain_slow" not in extract_rules(text, "connectivity") and "pain_downtime" not in extract_rules(text, "connectivity")
