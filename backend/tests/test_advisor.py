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
    assert extract_rules("yes", "fibre")["fibre_available"] is True
    assert extract_rules("no", "fibre")["fibre_available"] is False
    assert extract_rules("nothing else", "extras")["no_more_needs"] is True
    assert extract_rules("5", "lines")["mobile_lines"] == 5
    assert extract_rules("₹4,500", "budget")["monthly_budget"] == 4500
    assert extract_rules("no fibre here", None)["fibre_available"] is False


def test_budget_and_priority_phrases():
    assert extract_rules("my budget is Rs 3000 per month", None)["monthly_budget"] == 3000
    assert extract_rules("something cheap please", None)["priority"] == "price"


def test_garbage_input_extracts_nothing():
    assert extract_rules("asdf qwer ???", None) == {}
    assert extract_rules("", None) == {}


def test_question_plan_terminates_and_skips_known_slots():
    needs, asked, order = {}, [], []
    for _ in range(10):
        q = next_question(needs, False, asked)
        if q is None:
            break
        order.append(q)
        asked.append(q)
    assert order[0] == "pain" and len(order) == len(set(order)) <= 7
    assert next_question({"wants": ["cctv"], "pain_downtime": True, "fibre_available": True, "mobile_lines": 2, "monthly_budget": 1000}, False, []) == "cameras"
    assert "budget" not in order or next_question({"monthly_budget": 5000}, False, ["pain", "extras", "fibre", "lines"]) is None


def test_merge_needs_ignores_invalid_values():
    n = merge_needs({"wants": ["sms"]}, {"wants": ["cctv", "hacking"], "cameras": -3, "mobile_lines": 2, "priority": "luxury", "fibre_available": "yes"})
    assert n == {"wants": ["cctv", "sms"], "mobile_lines": 2}


def test_llm_text_with_invented_amount_or_product_is_rejected():
    facts = {"monthly_total_incl_gst": 4130.0, "items": [{"name": "Biz Fibre 100"}]}
    assert reply_is_grounded("Your plan is ₹4,130 a month.", facts, "")
    assert not reply_is_grounded("Your plan is just ₹999 a month!", facts, "")
    assert not reply_is_grounded("Add P25 for ₹4130", facts, "")
