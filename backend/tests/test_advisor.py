"""Advisor: slot extraction (English/Hindi), question planning, and the guard that stops an LLM inventing prices."""
from app.services.advisor.providers import reply_is_grounded
from app.services.advisor.slots import extract_rules, merge_needs, next_question


def test_extracts_needs_and_quantities_from_english():
    u = extract_rules("We need 4 cameras, whatsapp for customers and a billing counter. Internet keeps going down", None)
    assert {"cctv", "whatsapp", "pos"} <= set(u["wants"])
    assert u["cameras"] == 4 and u["pain_downtime"] is True


def test_extracts_needs_from_hindi():
    u = extract_rules("मुझे 6 कैमरे और व्हाट्सऐप चाहिए, नेट बंद हो जाता है", None)
    assert {"cctv", "whatsapp"} <= set(u["wants"]) and u["cameras"] == 6 and u["pain_downtime"]


def test_short_answers_are_read_in_context():
    assert extract_rules("yes", "connectivity")["fibre_available"] is True
    assert extract_rules("no", "connectivity")["fibre_available"] is False
    assert extract_rules("nothing", "channels")["_declined"] == "channels"
    assert extract_rules("yes", "channels")["_clarify"] == "channels"  # a bare yes to an open question: ask WHICH
    assert extract_rules("5", "pos")["pos_counters"] == 5
    assert extract_rules("₹4,500", "budget")["monthly_budget"] == 4500
    assert extract_rules("no fibre here", None)["fibre_available"] is False


def test_budget_and_priority_phrases():
    assert extract_rules("my budget is Rs 3000 per month", None)["monthly_budget"] == 3000
    assert extract_rules("something cheap please", None)["priority"] == "price"


def test_garbage_input_extracts_nothing():
    assert extract_rules("asdf qwer ???", None) == {}
    assert extract_rules("", None) == {}


def test_question_plan_terminates_skips_known_slots_and_never_repeats():
    needs, asked, order = {}, [], []
    for _ in range(12):
        q = next_question(needs, False, asked)
        if q is None:
            break
        order.append(q)
        asked.append(q)
    assert order[0] == "pain" and len(order) == len(set(order)) <= 8
    # what the customer already said is never asked again
    assert next_question({"wants": ["cctv"], "pain_downtime": True, "fibre_available": True, "monthly_budget": 1000}, False, []) == "cameras"
    assert "connectivity" not in order[:0] and next_question({"connectivity": "fibre", "fibre_available": True, "pain_slow": True}, False, []) != "connectivity"
    assert next_question({"monthly_budget": 5000, "pain_slow": True, "fibre_available": True, "declined": ["channels", "physical", "office"]}, False, []) is None


def test_merge_needs_ignores_invalid_values():
    n = merge_needs({"wants": ["sms"]}, {"wants": ["cctv", "hacking"], "cameras": -3, "mobile_lines": 2, "priority": "luxury", "fibre_available": "yes"})
    assert n == {"wants": ["cctv", "sms"], "mobile_lines": 2}
    # an explicit "no X" removes X, and changing their mind brings it back
    n = merge_needs({"wants": ["cctv", "sms"]}, {"rejects": ["cctv"]})
    assert n["wants"] == ["sms"] and n["rejects"] == ["cctv"]
    assert "cctv" in merge_needs(n, {"wants": ["cctv"]})["wants"] and "rejects" not in merge_needs(n, {"wants": ["cctv"]})


def test_llm_text_with_invented_amount_or_product_is_rejected():
    facts = {"monthly_total_incl_gst": 4130.0, "items": [{"name": "Biz Fibre 100"}]}
    assert reply_is_grounded("Your plan is ₹4,130 a month.", facts, "")
    assert not reply_is_grounded("Your plan is just ₹999 a month!", facts, "")
    assert not reply_is_grounded("Add P25 for ₹4130", facts, "")


# ---- free-form conversation (no LLM key): answers what the customer said instead of replaying the script ----

def _chat(client, *texts):
    j = client.post("/api/journeys", json={"business_name": "Sharma Traders", "business_type": "Retail", "city": "Pune", "employees": 8, "sites": 1, "current_internet": "Home broadband"}).json()
    client.post(f"/api/journeys/{j['id']}/advisor/start")
    out = [client.post(f"/api/journeys/{j['id']}/advisor/message", json={"text": t}).json() for t in texts]
    return j["id"], out


def test_replies_follow_the_customers_words_not_the_script(client):
    _, (hi, can_do, night, off_topic) = _chat(client, "hi", "what can you do for me?", "is there night support?", "what's the weather today?")
    assert hi["reply"].startswith("Hello!") and "?" in hi["reply"]
    assert "Connectivity" in can_do["reply"]
    assert "won't guess" in night["reply"]
    assert "rather not guess" in off_topic["reply"]
    assert len({r["reply"] for r in (hi, can_do, night, off_topic)}) == 4
    for r in (hi, can_do, night, off_topic):  # unanswered question is re-asked, state does not advance
        assert r["question"] == "pain" and not r["recommendation_ready"]


def test_asking_about_a_product_explains_it_without_adding_it(client):
    jid, (explain,) = _chat(client, "what is cloud CCTV?")
    assert "Cloud CCTV" in explain["reply"] and "per camera" in explain["reply"] and "₹" in explain["reply"]
    assert "cctv" not in client.get(f"/api/journeys/{jid}").json()["needs"].get("wants", [])
    _, (added,) = _chat(client, "I need 3 cameras")
    assert "3 cameras" in added["reply"]


def test_after_recommendation_questions_are_answered_from_the_quote(client):
    jid, outs = _chat(client, "I need 3 cameras and whatsapp", "recommend", "how much is the total?", "is gst included?", "contract length?", "setup time?")
    assert outs[1]["recommendation_ready"]
    selection_before = client.get(f"/api/journeys/{jid}").json()["selection"]
    total, gst, contract, setup = (o["reply"] for o in outs[2:])
    monthly = outs[1]["summary"]["monthly_total"]
    assert f"{monthly:,.0f}" in total or f"{monthly:,.2f}" in total
    assert "18%" in gst and "12-month" in contract and "days" in setup
    assert client.get(f"/api/journeys/{jid}").json()["selection"] == selection_before  # Q&A never changes the basket


def test_why_do_i_need_x_is_a_question_not_a_request(client):
    from app.services.advisor.qa import is_info_question

    assert is_info_question("why do I need failover?") and is_info_question("what is cloud CCTV?")
    assert not is_info_question("I need 3 cameras") and not is_info_question("can you add cloud backup?")
    _, (_, why) = _chat(client, "recommend", "why do I need failover?")
    assert "failover" in why["reply"].lower() and "recommended **" not in why["reply"]


# ---- Gemini provider (HTTP faked: no network, no key) ----

def _gemini_with(handler):
    import httpx

    from app.services.advisor.providers import GeminiProvider

    g = GeminiProvider.__new__(GeminiProvider)
    g.model, g.models, g._good, g._key = "test-model", ["test-model"], 0, "secret-key"
    g.http = httpx.Client(transport=httpx.MockTransport(handler))
    return g


def test_gemini_extract_parses_json_and_keeps_key_out_of_url():
    import httpx

    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), req.content.decode()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '```json\n{"wants": ["cctv"], "cameras": 4, "bogus": 1}\n```'}]}}]})

    out = _gemini_with(handler).extract("mujhe 4 camere chahiye", [], {}, None)
    assert out["cameras"] == 4 and "cctv" in out["wants"] and "bogus" not in out
    assert seen["key"] == "secret-key" and "secret-key" not in seen["url"] and "application/json" in seen["body"]


def test_gemini_failures_fall_back_to_rules_and_templates():
    import httpx

    g = _gemini_with(lambda req: httpx.Response(429, json={"error": {"message": "quota"}}))
    assert g.extract("we need 4 cameras", [], {}, None)["cameras"] == 4  # rules still work
    assert g.answer("hello?", {}, [], "en") is None and g.phrase("t", {}, [], "en") is None  # engine then uses its templates


def test_gemini_selected_only_when_keyed(monkeypatch):
    from app.config import get_settings
    from app.services.advisor import providers

    s = get_settings()
    monkeypatch.setattr(providers, "_provider_cache", {})
    monkeypatch.setattr(s, "llm_provider", "auto")
    monkeypatch.setattr(s, "anthropic_api_key", "")
    monkeypatch.setattr(s, "gemini_api_key", "")
    assert providers.get_provider().name == "mock"
    monkeypatch.setattr(s, "gemini_api_key", "AIza-test")
    assert providers.get_provider().name == "gemini"


# ---- regressions from a live chat: goodbye kept getting a question; "hi" got an improvised recommendation ----

def test_goodbye_closes_politely_without_another_question(client):
    jid, (_, bye) = _chat(client, "I need 3 cameras", "i dont need any thing bye bye")
    assert bye["question"] is None and "?" not in bye["reply"] and bye["reply"].startswith("No problem")
    assert "Show my recommendation" in bye["chips"]
    _, (still_ok,) = _chat(client, "I need 4 cameras, bye")  # a need plus bye is still a need
    assert "4 cameras" in still_ok["reply"]


def test_i_dont_need_anything_stops_the_questions_and_recommends(client):
    _, (_, done) = _chat(client, "I need 3 cameras", "i dont need anything")
    assert done["recommendation_ready"] and "₹" in done["reply"]


def test_llm_cannot_improvise_a_recommendation_for_a_greeting_or_question(client, monkeypatch):
    from app.services.advisor import engine

    class Chatty:
        name = "gemini"
        def extract(self, *a):  # noqa: E301
            return {}
        def phrase(self, *a):  # noqa: E301
            return None
        def answer(self, text, *a):  # noqa: E301
            return "Hello! I recommend the Biz 5G AirFiber 100 at 899.0 to 1099.0 INR per month."

    monkeypatch.setattr(engine, "get_provider", lambda: Chatty())
    _, (hi, q) = _chat(client, "hi", "which plan is best for a bakery?")
    assert hi["provider"] == q["provider"] == "gemini"  # the fake LLM really was in charge
    assert "recommend the Biz" not in hi["reply"] and hi["reply"].startswith("Hello!") and "INR" not in hi["reply"]
    assert "recommend the Biz" not in q["reply"] and "INR" not in q["reply"]  # rejected -> rules answer instead


def test_amounts_written_after_the_number_are_also_checked():
    facts = {"monthly_total_incl_gst": 4130.0}
    assert reply_is_grounded("That is ₹4,130 a month, 4130 INR in total.", facts, "")
    assert not reply_is_grounded("It costs 999 INR a month", facts, "")
    assert not reply_is_grounded("It costs 899.0 to 1099.0 rupees", facts, "")


def test_greeting_after_goodbye_is_a_greeting_even_if_the_llm_misreads_history(client, monkeypatch):
    from app.services.advisor import engine

    class Confused:
        name = "gemini"
        def extract(self, *a):  # noqa: E301
            return {"no_more_needs": True}  # what a model did with "hi" after an earlier "bye"
        def phrase(self, *a):  # noqa: E301
            return None
        def answer(self, *a):  # noqa: E301
            return None

    monkeypatch.setattr(engine, "get_provider", lambda: Confused())
    _, (_, hi) = _chat(client, "bye", "hi")
    assert hi["reply"].startswith("Hello!") and not hi["recommendation_ready"]


def test_explicit_recommendation_request_reaches_the_engine_even_with_an_llm(client, monkeypatch):
    from app.services.advisor import engine

    class Chatty:
        name = "gemini"
        def extract(self, *a):  # noqa: E301
            return {}
        def phrase(self, *a):  # noqa: E301
            return None
        def answer(self, *a):  # noqa: E301
            return "Sure! Would you like guest Wi-Fi?"

    monkeypatch.setattr(engine, "get_provider", lambda: Chatty())
    _, (rec,) = _chat(client, "ok show me the recommendation")
    assert rec["recommendation_ready"] and "₹" in rec["reply"]


def test_only_one_question_per_reply(client, monkeypatch):
    from app.services.advisor import engine

    class Asker:
        name = "gemini"
        def extract(self, *a):  # noqa: E301
            return {}
        def phrase(self, *a):  # noqa: E301
            return None
        def answer(self, *a):  # noqa: E301
            return "We have POS and CCTV for bakeries. What do you need?"

    monkeypatch.setattr(engine, "get_provider", lambda: Asker())
    _, (r,) = _chat(client, "which plan is best for a bakery?")
    assert r["reply"].count("?") == 1
