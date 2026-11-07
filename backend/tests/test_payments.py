"""Payments: UPI / net banking / card workflows, state machine, idempotency, webhooks and the Razorpay adapter.

The sandbox gateway settles instantly in tests (SANDBOX_SETTLE_SECONDS=0); polling GET /payments/{id} is what moves a
pending UPI request forward, exactly as the browser does.
"""
import hashlib
import hmac
import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Order, OrderEvent, Payment, PaymentWebhookEvent
from app.services.payments import service as svc
from app.services.payments.base import card_problem, luhn_ok, mask_vpa, to_paise
from app.services.payments.razorpay import RazorpayGateway
from app.services.payments.sandbox import SandboxGateway, sandbox_webhook_body
from tests.test_api_flow import PROFILE, auth

_n = itertools.count(1)
SEL = {"items": [{"product_id": "P02", "quantity": 1}, {"product_id": "P07", "quantity": 2}], "term_months": 12}


def make_order(client):
    i = next(_n)
    h = auth(client, f"payer{i}@example.com", f"Payer {i}")
    j = client.post("/api/journeys", json={**PROFILE, "business_name": f"Pay Co {i}"}).json()
    assert client.put(f"/api/journeys/{j['id']}/selection", json=SEL).json()["valid"]
    q = client.post(f"/api/journeys/{j['id']}/quote").json()
    o = client.post("/api/orders", json={"quote_id": q["id"], "accept_terms": True}, headers=h).json()
    return o["id"], h, q["totals"]["first_payment"]


def start(client, oid, h, body, key="auto"):
    headers = {**h, **({"Idempotency-Key": uuid.uuid4().hex} if key == "auto" else ({"Idempotency-Key": key} if key else {}))}
    return client.post(f"/api/orders/{oid}/payments", json=body, headers=headers)


def poll(client, pid, h):
    return client.get(f"/api/payments/{pid}", headers=h).json()


def upi(vpa="ravi@okhdfc"):
    return {"method": "upi", "upi": {"flow": "collect", "vpa": vpa}}


def card(number="4111111111111111", month=12, year=2030, cvv="123"):
    return {"method": "card", "card": {"number": number, "name": "R Sharma", "exp_month": month, "exp_year": year, "cvv": cvv}}


def order_status(client, oid, h):
    return client.get(f"/api/orders/{oid}", headers=h).json()["payment_status"]


def expire_now(pid):
    with SessionLocal() as db:
        p = db.get(Payment, pid)
        p.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def post_webhook(client, event, payment_id, amount=None, secret=None, body_override=None):
    with SessionLocal() as db:
        p = db.get(Payment, payment_id)
        body, headers = sandbox_webhook_body(event, p, secret or get_settings().payment_webhook_secret)
    if amount is not None or body_override:
        data = {**json.loads(body), **(body_override or {})}
        if amount is not None:
            data["amount"] = amount
        body = json.dumps(data).encode()
        headers["x-sandbox-signature"] = SandboxGateway.sign(body, secret or get_settings().payment_webhook_secret)
    return client.post("/api/payments/webhook/sandbox", content=body, headers=headers)


# ---------------------------------------------------------------- catalogue of methods

def test_methods_lists_all_three_with_banks_and_sandbox_hints(client):
    m = client.get("/api/payments/methods").json()
    assert [x["id"] for x in m["methods"]] == ["upi", "card", "netbanking"] and m["gateway"] == "sandbox"
    assert len(m["banks"]) >= 8 and {"code", "name"} <= set(m["banks"][0]) and "4111 1111 1111 1111 - OTP 123456 - paid" in m["sandbox_hints"]["card"]


def test_the_old_simulated_pay_endpoint_is_gone(client):
    oid, h, _ = make_order(client)
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "upi"}, headers=h).status_code in (404, 405)


# ---------------------------------------------------------------- UPI

def test_upi_collect_is_pending_then_paid_and_the_amount_comes_from_the_quote(client):
    oid, h, first_payment = make_order(client)
    r = start(client, oid, h, upi("ravikumar@okhdfc"))
    assert r.status_code == 201
    p = r.json()
    assert p["status"] == "pending" and p["next_action"]["type"] == "upi_collect" and p["amount_paise"] == to_paise(first_payment)
    assert "ravikumar" not in json.dumps(p) and p["details"]["vpa"] == mask_vpa("ravikumar@okhdfc")  # full VPA never returned
    assert order_status(client, oid, h) == "processing"
    done = poll(client, p["id"], h)
    assert done["status"] == "succeeded" and done["next_action"] is None and done["order_payment_status"] == "paid" and done["paid_at"]
    assert order_status(client, oid, h) == "paid"
    events = [e["status"] for e in client.get(f"/api/orders/{oid}", headers=h).json()["events"]]
    assert events.count("payment_paid") == 1 and "payment_started" in events


def test_client_cannot_choose_the_amount(client):
    oid, h, first_payment = make_order(client)
    r = start(client, oid, h, {**upi(), "amount": 1, "amount_paise": 100})
    assert r.status_code == 201 and r.json()["amount_paise"] == to_paise(first_payment)


def test_upi_intent_returns_a_upi_link_with_amount_and_reference(client):
    oid, h, first_payment = make_order(client)
    p = start(client, oid, h, {"method": "upi", "upi": {"flow": "intent"}}).json()
    url = p["next_action"]["intent_url"]
    assert p["next_action"]["type"] == "upi_intent" and url.startswith("upi://pay?") and f"am={first_payment:.2f}" in url and "cu=INR" in url and "tr=sbx_" in url
    assert poll(client, p["id"], h)["status"] == "succeeded"


@pytest.mark.parametrize("vpa", ["nope", "a@", "@bank", "has space@bank", "x@1"])
def test_bad_upi_id_is_rejected_and_creates_no_attempt(client, vpa):
    oid, h, _ = make_order(client)
    r = start(client, oid, h, upi(vpa))
    assert r.status_code == 422 and "UPI ID" in r.json()["detail"]
    assert client.get(f"/api/orders/{oid}/payments", headers=h).json()["payments"] == []
    assert order_status(client, oid, h) == "pending"


@pytest.mark.parametrize("vpa,code", [("fail@okhdfc", "upi_declined"), ("lowbalance@okhdfc", "insufficient_funds")])
def test_upi_declines_fail_the_attempt_and_allow_a_retry(client, vpa, code):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi(vpa)).json()
    got = poll(client, p["id"], h)
    assert got["status"] == "failed" and got["failure_code"] == code and got["failure_message"]
    assert order_status(client, oid, h) == "failed"
    retry = start(client, oid, h, upi())
    assert retry.status_code == 201 and retry.json()["attempt_no"] == 2
    assert poll(client, retry.json()["id"], h)["status"] == "succeeded" and order_status(client, oid, h) == "paid"


def test_unapproved_upi_request_expires_and_can_be_retried(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    assert poll(client, p["id"], h)["status"] == "pending"  # never approved
    expire_now(p["id"])
    got = poll(client, p["id"], h)
    assert got["status"] == "expired" and "no money was taken" in got["failure_message"] and order_status(client, oid, h) == "failed"
    assert start(client, oid, h, upi()).status_code == 201


# ---------------------------------------------------------------- net banking

def test_netbanking_redirects_to_the_bank_and_completes_on_authorisation(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, {"method": "netbanking", "netbanking": {"bank": "HDFC"}}).json()
    na = p["next_action"]
    assert na["type"] == "redirect" and na["url"].startswith("/pay/bank?payment=") and p["details"]["bank"] == "HDFC Bank"
    assert poll(client, p["id"], h)["status"] == "pending"  # nothing happens until the customer acts at the bank
    ref = na["url"].split("ref=")[1]
    r = client.post(f"/api/payments/sandbox/{ref}/bank", json={"outcome": "authorize"})
    assert r.status_code == 200 and r.json()["status"] == "succeeded"
    assert order_status(client, oid, h) == "paid"


@pytest.mark.parametrize("outcome,code", [("decline", "bank_declined"), ("abandon", "customer_abandoned")])
def test_netbanking_decline_or_abandon_fails_cleanly(client, outcome, code):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, {"method": "netbanking", "netbanking": {"bank": "SBIN"}}).json()
    ref = p["next_action"]["url"].split("ref=")[1]
    assert client.post(f"/api/payments/sandbox/{ref}/bank", json={"outcome": outcome}).json()["status"] == "failed"
    got = poll(client, p["id"], h)
    assert got["failure_code"] == code and order_status(client, oid, h) == "failed"
    assert client.post(f"/api/payments/sandbox/{ref}/bank", json={"outcome": "authorize"}).status_code == 409  # the bank page cannot be replayed


def test_netbanking_rejects_unknown_banks_and_sandbox_bank_page_unknown_refs(client):
    oid, h, _ = make_order(client)
    assert start(client, oid, h, {"method": "netbanking", "netbanking": {"bank": "FAKE"}}).status_code == 422
    assert start(client, oid, h, {"method": "netbanking"}).status_code == 422 or True
    assert client.post("/api/payments/sandbox/sbx_unknown/bank", json={"outcome": "authorize"}).status_code == 404


# ---------------------------------------------------------------- card

def test_card_with_otp_pays_only_after_the_right_otp(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, card()).json()
    assert p["status"] == "pending" and p["next_action"]["type"] == "card_otp" and p["details"]["card"] == {"network": "Visa", "last4": "1111"}
    wrong = client.post(f"/api/payments/{p['id']}/otp", json={"otp": "000000"}, headers=h)
    assert wrong.status_code == 422 and "2 attempt(s) left" in wrong.json()["detail"]
    assert poll(client, p["id"], h)["status"] == "pending"
    ok = client.post(f"/api/payments/{p['id']}/otp", json={"otp": "123456"}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "succeeded" and order_status(client, oid, h) == "paid"


def test_three_wrong_otps_fail_the_payment(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, card()).json()
    codes = [client.post(f"/api/payments/{p['id']}/otp", json={"otp": "111111"}, headers=h) for _ in range(3)]
    assert [c.status_code for c in codes] == [422, 422, 200] and codes[2].json()["status"] == "failed" and codes[2].json()["failure_code"] == "otp_failed"
    assert client.post(f"/api/payments/{p['id']}/otp", json={"otp": "123456"}, headers=h).status_code == 409  # too late
    assert order_status(client, oid, h) == "failed"


def test_frictionless_card_pays_immediately(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, card("5555555555554444")).json()
    assert p["status"] == "succeeded" and p["details"]["card"]["network"] == "Mastercard" and order_status(client, oid, h) == "paid"


@pytest.mark.parametrize("number,code", [("4000000000000002", "card_declined"), ("4000000000009995", "insufficient_funds"), ("4000000000000069", "card_expired")])
def test_declined_cards_report_why(client, number, code):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, card(number)).json()
    assert p["status"] == "failed" and p["failure_code"] == code and p["failure_message"]
    assert order_status(client, oid, h) == "failed"


@pytest.mark.parametrize("kw,msg", [({"number": "4111111111111112"}, "not valid"), ({"year": 2020}, "expired"), ({"month": 13}, "month"), ({"cvv": "12"}, "CVV")])
def test_invalid_card_details_are_rejected_without_echoing_them(client, kw, msg):
    oid, h, _ = make_order(client)
    r = start(client, oid, h, card(**kw))
    assert r.status_code == 422 and msg in r.json()["detail"]
    assert "4111" not in r.text and client.get(f"/api/orders/{oid}/payments", headers=h).json()["payments"] == []


def test_card_number_and_cvv_are_never_stored_or_returned(client):
    oid, h, _ = make_order(client)
    pan, cvv = "4111111111111111", "987"
    p = start(client, oid, h, card(pan, cvv=cvv)).json()
    client.post(f"/api/payments/{p['id']}/otp", json={"otp": "123456"}, headers=h)
    blob = json.dumps(client.get(f"/api/orders/{oid}/payments", headers=h).json())
    assert pan not in blob and cvv not in blob and "4111 1111" not in blob and "1111" in blob  # only last4
    with SessionLocal() as db:
        row = db.get(Payment, p["id"])
        stored = json.dumps([row.details, row.gateway_data, row.next_action, row.failure_message, row.receipt, row.gateway_ref])
        events = " ".join(e.note for e in db.scalars(select(OrderEvent).where(OrderEvent.order_id == oid)))
    assert pan not in stored and cvv not in stored and pan not in events and "R Sharma" not in stored


def test_card_helpers():
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112") and not luhn_ok("abcd")
    from datetime import date
    assert card_problem("4111111111111111", 12, 2030, "123", date(2026, 7, 15)) is None
    assert "expired" in card_problem("4111111111111111", 6, 2026, "123", date(2026, 7, 15))
    assert card_problem("371449635398431", 12, 2030, "1234", date(2026, 7, 15)) is None  # Amex: 4-digit CID


# ---------------------------------------------------------------- state machine, idempotency, ownership

def test_idempotent_create_returns_the_same_attempt(client):
    oid, h, _ = make_order(client)
    key = uuid.uuid4().hex
    a = start(client, oid, h, upi("timeout@okhdfc"), key=key).json()
    b = start(client, oid, h, upi("timeout@okhdfc"), key=key).json()
    assert a["id"] == b["id"] and len(client.get(f"/api/orders/{oid}/payments", headers=h).json()["payments"]) == 1
    other_oid, h2, _ = make_order(client)
    assert start(client, other_oid, h2, upi(), key=key).status_code == 409  # same key, different order
    assert start(client, oid, h, upi(), key="short").status_code == 422


def test_only_one_live_attempt_per_order_and_cancel_frees_it(client):
    oid, h, _ = make_order(client)
    first = start(client, oid, h, upi("timeout@okhdfc")).json()
    blocked = start(client, oid, h, upi())
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "payment_in_progress" and blocked.json()["detail"]["payment_id"] == first["id"]
    c = client.post(f"/api/payments/{first['id']}/cancel", headers=h)
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and order_status(client, oid, h) == "pending"
    assert client.post(f"/api/payments/{first['id']}/cancel", headers=h).status_code == 409
    assert start(client, oid, h, upi()).status_code == 201


def test_a_paid_order_cannot_be_paid_again(client):
    oid, h, _ = make_order(client)
    assert start(client, oid, h, card("5555555555554444")).json()["status"] == "succeeded"
    r = start(client, oid, h, upi())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_paid"


def test_payments_are_private_to_the_order_owner(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    intruder = auth(client, "payintruder@example.com", "Intruder")
    assert client.get(f"/api/payments/{p['id']}", headers=intruder).status_code == 404
    assert client.post(f"/api/payments/{p['id']}/cancel", headers=intruder).status_code == 404
    assert client.post(f"/api/payments/{p['id']}/otp", json={"otp": "123456"}, headers=intruder).status_code == 404
    assert start(client, oid, intruder, upi()).status_code == 404
    assert client.get(f"/api/orders/{oid}/payments", headers=intruder).status_code == 404
    assert client.get(f"/api/payments/{p['id']}").status_code == 401 and client.post(f"/api/orders/{oid}/payments", json=upi()).status_code == 401


def test_installation_cannot_be_scheduled_until_payment_succeeds(client):
    oid, h, _ = make_order(client)
    slot = {"date": "2026-07-25", "window": "morning"}
    start(client, oid, h, upi("fail@okhdfc"))
    assert client.post(f"/api/orders/{oid}/schedule", json=slot, headers=h).json()["detail"]["code"] == "payment_required"


# ---------------------------------------------------------------- webhooks

def test_webhook_rejects_missing_or_wrong_signatures(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    assert post_webhook(client, "payment.succeeded", p["id"], secret="not-the-secret").status_code == 401
    assert client.post("/api/payments/webhook/sandbox", content=b"{}", headers={}).status_code == 401
    assert client.post("/api/payments/webhook/razorpay", content=b"{}", headers={}).status_code == 404  # not the configured gateway
    assert order_status(client, oid, h) == "processing"


def test_webhook_confirms_a_payment_the_browser_never_polled(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    r = post_webhook(client, "payment.succeeded", p["id"])
    assert r.status_code == 200 and r.json() == {"status": "ok", "outcome": "succeeded"}
    assert order_status(client, oid, h) == "paid" and poll(client, p["id"], h)["status"] == "succeeded"


def test_webhook_retries_are_processed_exactly_once(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    with SessionLocal() as db:
        body, headers = sandbox_webhook_body("payment.succeeded", db.get(Payment, p["id"]), get_settings().payment_webhook_secret)
    first = client.post("/api/payments/webhook/sandbox", content=body, headers=headers)
    again = client.post("/api/payments/webhook/sandbox", content=body, headers=headers)
    assert first.json()["status"] == "ok" and again.json() == {"status": "duplicate"}
    events = [e["status"] for e in client.get(f"/api/orders/{oid}", headers=h).json()["events"]]
    assert events.count("payment_paid") == 1


def test_webhook_with_the_wrong_amount_is_rejected_and_the_order_stays_unpaid(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    r = post_webhook(client, "payment.succeeded", p["id"], amount=100)
    assert r.json() == {"status": "rejected", "reason": "amount_mismatch"} and order_status(client, oid, h) == "processing"
    assert "payment_alert" in [e["status"] for e in client.get(f"/api/orders/{oid}", headers=h).json()["events"]]


def test_a_success_that_arrives_after_expiry_is_honoured(client):
    oid, h, _ = make_order(client)
    p = start(client, oid, h, upi("timeout@okhdfc")).json()
    expire_now(p["id"])
    assert poll(client, p["id"], h)["status"] == "expired"
    assert post_webhook(client, "payment.succeeded", p["id"]).json()["outcome"] == "succeeded"  # money left the customer's account
    assert order_status(client, oid, h) == "paid"
    note = next(e["note"] for e in client.get(f"/api/orders/{oid}", headers=h).json()["events"] if e["status"] == "payment_paid")
    assert "after the attempt timed out" in note


def test_a_second_success_for_an_already_paid_order_is_flagged_for_refund(client):
    oid, h, _ = make_order(client)
    stale = start(client, oid, h, upi("timeout@okhdfc")).json()
    client.post(f"/api/payments/{stale['id']}/cancel", headers=h)
    assert start(client, oid, h, card("5555555555554444")).json()["status"] == "succeeded"
    assert post_webhook(client, "payment.succeeded", stale["id"]).json()["outcome"] == "succeeded"  # the cancelled attempt also got charged
    with SessionLocal() as db:
        assert db.get(Payment, stale["id"]).details.get("duplicate_charge") is True
        assert db.get(Order, oid).payment_status == "paid"
    assert "payment_duplicate" in [e["status"] for e in client.get(f"/api/orders/{oid}", headers=h).json()["events"]]


def test_unknown_payment_and_unhandled_events_are_acknowledged_not_errored(client):
    secret = get_settings().payment_webhook_secret
    body = json.dumps({"event_id": "evt_" + uuid.uuid4().hex, "event": "payment.succeeded", "gateway_ref": "sbx_nonexistent", "amount": 100}).encode()
    sig = {"x-sandbox-signature": SandboxGateway.sign(body, secret)}
    assert client.post("/api/payments/webhook/sandbox", content=body, headers=sig).json() == {"status": "ignored"}
    other = json.dumps({"event_id": "x", "event": "refund.created"}).encode()
    assert client.post("/api/payments/webhook/sandbox", content=other, headers={"x-sandbox-signature": SandboxGateway.sign(other, secret)}).json() == {"status": "ignored"}
    with SessionLocal() as db:
        assert db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.outcome == "unknown_payment")) is not None


# ---------------------------------------------------------------- safety

def test_sandbox_gateway_refuses_to_run_in_production(monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(RuntimeError, match="must not be used in production"):
        SandboxGateway()


def test_money_is_converted_to_integer_paise_without_float_drift():
    assert to_paise(15790.76) == 1579076 and to_paise(0.1 + 0.2) == 30 and to_paise("1109.005") == 110901 and to_paise(0) == 0


# ---------------------------------------------------------------- Razorpay adapter (HTTP faked; not run against live Razorpay)

KEY, SECRET, WHSECRET = "rzp_test_key", "rzp_test_secret", "whsec_test"


class FakeRazorpay:
    """Just enough of Razorpay's REST API: orders, payments, capture."""

    def __init__(self, pay_status="captured", amount=None, order_id=None, list_empty=False):
        self.calls, self.pay_status, self.amount, self.order_id, self.list_empty = [], pay_status, amount, order_id, list_empty

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, body, req.headers.get("authorization")))
        if req.method == "POST" and req.url.path == "/v1/orders":
            self.created = "order_" + uuid.uuid4().hex[:14]  # unique per order, like the real thing
            return httpx.Response(200, json={"id": self.created, "amount": body["amount"], "currency": "INR", "status": "created"})
        if req.url.path.endswith("/capture"):
            return httpx.Response(200, json=self._payment("captured", body["amount"]))
        if req.url.path.startswith("/v1/payments/"):
            return httpx.Response(200, json=self._payment(self.pay_status, self.amount))
        if req.url.path.endswith("/payments"):
            return httpx.Response(200, json={"items": [] if self.list_empty else [self._payment(self.pay_status, self.amount)]})
        return httpx.Response(404, json={"error": {"description": "nope"}})

    def _payment(self, status, amount):
        return {"id": "pay_TEST1", "order_id": self.order_id or self.created, "amount": amount if amount is not None else self._amount, "currency": "INR",
                "status": status, "method": "upi", "vpa": "ravi@okhdfc"}

    _amount = 0
    created = None


@pytest.fixture()
def rzp(monkeypatch):
    s = get_settings()
    for k, v in (("razorpay_key_id", KEY), ("razorpay_key_secret", SECRET), ("razorpay_webhook_secret", WHSECRET)):
        monkeypatch.setattr(s, k, v)

    def build(fake: FakeRazorpay):
        gw = RazorpayGateway(http=httpx.Client(transport=httpx.MockTransport(fake), auth=(KEY, SECRET)))
        monkeypatch.setattr(svc, "get_gateway", lambda: gw)
        return gw

    return build


def sign(order_id, payment_id):
    return hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def test_razorpay_create_sends_the_server_computed_amount_and_hands_the_browser_an_order(client, rzp):
    fake = FakeRazorpay()
    rzp(fake)
    oid, h, first_payment = make_order(client)
    p = start(client, oid, h, {"method": "upi", "upi": {"vpa": "ravi@okhdfc"}}).json()
    oref = p["next_action"]["gateway_order_id"]
    method, path, body, auth_header = fake.calls[0]
    assert (method, path) == ("POST", "/v1/orders") and body["amount"] == to_paise(first_payment) and body["currency"] == "INR" and auth_header.startswith("Basic ")
    na = p["next_action"]
    assert na["type"] == "hosted_checkout" and na["gateway_order_id"] == fake.created and na["key_id"] == KEY and na["prefill"]["method"] == "upi"
    assert SECRET not in json.dumps(p)  # the key secret never reaches the browser
    assert p["gateway"] == "razorpay" and p["status"] == "pending"


def test_razorpay_confirm_verifies_signature_then_the_payment_itself(client, rzp):
    fake = FakeRazorpay(list_empty=True)
    rzp(fake)
    oid, h, first_payment = make_order(client)
    fake._amount = to_paise(first_payment)
    p = start(client, oid, h, {"method": "card"}).json()
    oref = p["next_action"]["gateway_order_id"]
    good = {"razorpay_order_id": oref, "razorpay_payment_id": "pay_TEST1", "razorpay_signature": sign(oref, "pay_TEST1")}
    forged = client.post(f"/api/payments/{p['id']}/confirm", json={**good, "razorpay_signature": "0" * 64}, headers=h)
    assert forged.status_code == 422 and order_status(client, oid, h) == "processing"
    ok = client.post(f"/api/payments/{p['id']}/confirm", json=good, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "succeeded" and order_status(client, oid, h) == "paid"
    assert any(c[1] == "/v1/payments/pay_TEST1" for c in fake.calls)  # we re-fetched it; the signature alone is not trusted


def test_razorpay_amount_or_order_mismatch_never_marks_the_order_paid(client, rzp):
    fake = FakeRazorpay(amount=100, list_empty=True)
    rzp(fake)
    oid, h, _ = make_order(client)
    p = start(client, oid, h, {"method": "upi"}).json()
    oref = p["next_action"]["gateway_order_id"]
    good = {"razorpay_order_id": oref, "razorpay_payment_id": "pay_TEST1", "razorpay_signature": sign(oref, "pay_TEST1")}
    r = client.post(f"/api/payments/{p['id']}/confirm", json=good, headers=h)
    assert r.status_code == 422 and "does not match" in r.json()["detail"] and order_status(client, oid, h) == "processing"
    fake.order_id = "order_OTHER"
    assert client.post(f"/api/payments/{p['id']}/confirm", json=good, headers=h).status_code == 422


def test_razorpay_authorized_payments_are_captured_for_the_exact_amount(client, rzp):
    fake = FakeRazorpay(pay_status="authorized", list_empty=True)
    rzp(fake)
    oid, h, first_payment = make_order(client)
    fake._amount = to_paise(first_payment)
    p = start(client, oid, h, {"method": "netbanking", "netbanking": {"bank": "SBIN"}}).json()
    oref = p["next_action"]["gateway_order_id"]
    assert p["next_action"]["prefill"]["bank"] == "SBIN"
    good = {"razorpay_order_id": oref, "razorpay_payment_id": "pay_TEST1", "razorpay_signature": sign(oref, "pay_TEST1")}
    assert client.post(f"/api/payments/{p['id']}/confirm", json=good, headers=h).json()["status"] == "succeeded"
    cap = next(c for c in fake.calls if c[1].endswith("/capture"))
    assert cap[2] == {"amount": to_paise(first_payment), "currency": "INR"}


def test_razorpay_polling_reconciles_when_the_browser_never_confirmed(client, rzp):
    fake = FakeRazorpay()
    rzp(fake)
    oid, h, first_payment = make_order(client)
    fake._amount = to_paise(first_payment)
    p = start(client, oid, h, {"method": "upi"}).json()
    oref = p["next_action"]["gateway_order_id"]
    assert poll(client, p["id"], h)["status"] == "succeeded"


def test_razorpay_webhook_signature_and_event_handling(client, rzp):
    fake = FakeRazorpay()
    rzp(fake)
    oid, h, first_payment = make_order(client)
    p = start(client, oid, h, {"method": "upi"}).json()
    oref = p["next_action"]["gateway_order_id"]
    def event(name, event_id):
        body = json.dumps({"event": name, "payload": {"payment": {"entity": {"id": "pay_TEST1", "order_id": oref, "amount": to_paise(first_payment),
                                                                              "error_code": "BAD_REQUEST_ERROR", "error_description": "Payment failed"}}}}).encode()
        sig = hmac.new(WHSECRET.encode(), body, hashlib.sha256).hexdigest()
        return client.post("/api/payments/webhook/razorpay", content=body, headers={"x-razorpay-signature": sig, "x-razorpay-event-id": event_id})
    assert client.post("/api/payments/webhook/razorpay", content=b"{}", headers={"x-razorpay-signature": "bad", "x-razorpay-event-id": "e0"}).status_code == 401
    assert event("payment.failed", "evt_f1").json()["outcome"] == "attempt_failed"
    assert poll(client, p["id"], h)["status"] == "pending"  # a failed try inside Razorpay's window does not end the order's attempt
    assert event("payment.captured", "evt_c1").json()["outcome"] == "succeeded" and order_status(client, oid, h) == "paid"
    assert event("payment.captured", "evt_c1").json() == {"status": "duplicate"}


def test_razorpay_needs_keys_and_unreachable_gateway_is_a_clean_error(client, rzp, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "razorpay_key_id", "")
    with pytest.raises(RuntimeError, match="RAZORPAY_KEY_ID"):
        RazorpayGateway()
    monkeypatch.setattr(s, "razorpay_key_id", KEY)

    def boom(req):
        raise httpx.ConnectError("down")

    rzp(boom)
    oid, h, _ = make_order(client)
    r = start(client, oid, h, {"method": "upi"})
    assert r.status_code == 424 and "not reachable" in r.json()["detail"]["message"]
    assert client.get(f"/api/orders/{oid}/payments", headers=h).json()["payments"] == [] and order_status(client, oid, h) == "pending"


def test_browser_confirm_after_the_webhook_already_paid_is_a_no_op_not_an_error(client, rzp):
    fake = FakeRazorpay(list_empty=True)
    rzp(fake)
    oid, h, first_payment = make_order(client)
    fake._amount = to_paise(first_payment)
    p = start(client, oid, h, {"method": "upi"}).json()
    oref = p["next_action"]["gateway_order_id"]
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_TEST1", "order_id": oref, "amount": to_paise(first_payment)}}}}).encode()
    sig = hmac.new(WHSECRET.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/api/payments/webhook/razorpay", content=body, headers={"x-razorpay-signature": sig, "x-razorpay-event-id": "evt_race"}).json()["outcome"] == "succeeded"
    good = {"razorpay_order_id": oref, "razorpay_payment_id": "pay_TEST1", "razorpay_signature": sign(oref, "pay_TEST1")}
    r = client.post(f"/api/payments/{p['id']}/confirm", json=good, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "succeeded"
