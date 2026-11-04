"""End-to-end API journey: onboarding -> advisor -> recommendation -> quote -> order -> KYC -> install -> activation."""
import pytest

from app.config import get_settings

DOCS = get_settings().data_dir / "kyc_documents"
PROFILE = {
    "business_name": "Ganesh Woodcraft", "business_type": "Furniture workshop", "city": "Nagpur", "employees": 12, "sites": 1,
    "current_internet": "Home broadband", "monthly_budget": 15000, "monthly_telecom_spend": 3000,
    "has_gstin": True, "gstin": "27XUIXG0767D1ZP", "has_udyam": True, "contact_name": "Joseph Singh", "phone": "9876543210", "language": "en",
}


def auth(client, email="owner@example.com", name="Owner"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "Passw0rd!x", "phone": "9876543210"})
    if r.status_code == 409:
        r = client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!x"})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def admin_headers(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.example", "password": "AdminPass#123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def journey(client):
    r = client.post("/api/journeys", json=PROFILE)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    m = client.get("/api/meta").json()
    assert any(c["city"] == "Nagpur" and c["tier"] == 2 for c in m["cities"])
    assert len(client.get("/api/catalogue").json()) == 25


def test_onboarding_derives_segment_and_validates_gstin(journey, client):
    assert journey["profile"]["segment"] == "Small manufacturers"
    assert journey["profile"]["gstin_status"] == "active"
    assert "gstin" not in journey["profile"] and journey["profile"]["gstin_masked"].startswith("27")
    assert 0 <= journey["propensity"] <= 100


@pytest.mark.parametrize("patch,msg", [
    ({"employees": 0}, "employees"),
    ({"city": "Atlantis"}, "city"),
    ({"gstin": "27XUIXG0767D1ZQ"}, "GSTIN"),   # bad checksum
    ({"phone": "12345"}, "phone"),
    ({"current_internet": "Carrier pigeon"}, "current_internet"),
])
def test_onboarding_rejects_bad_input(client, patch, msg):
    r = client.post("/api/journeys", json={**PROFILE, **patch})
    assert r.status_code == 422 and msg.lower() in r.json()["detail"].lower()


def test_advisor_conversation_reaches_recommendation(client, journey):
    jid = journey["id"]
    start = client.post(f"/api/journeys/{jid}/advisor/start").json()
    assert "Joseph" in start["messages"][0]["content"] and start["question"]
    replies = ["Internet keeps going down, it is slow", "I need 4 cameras and billing, also whatsapp", "Yes fibre is available", "3 sims", "recommend"]
    last = None
    for text in replies:
        r = client.post(f"/api/journeys/{jid}/advisor/message", json={"text": text})
        assert r.status_code == 200, r.text
        last = r.json()
        if last["recommendation_ready"]:
            break
    assert last["recommendation_ready"], last
    assert "₹" in last["reply"] and last["provider"] == "mock"
    hist = client.get(f"/api/journeys/{jid}/advisor").json()["messages"]
    assert hist[0]["role"] == "assistant" and any(m["role"] == "user" for m in hist)


def test_recommendations_use_catalogue_and_respect_eligibility(client, journey):
    r = client.get(f"/api/journeys/{journey['id']}/recommendations").json()
    rec = r["recommendation"]
    ids = {i["product_id"] for i in rec["tiers"]["recommended"]["items"]}
    assert {"P23", "P19", "P15"} <= ids  # cameras, billing, whatsapp were asked for; GSTIN is active so WhatsApp is allowed
    assert any(c["product_id"] == "P03" and c["eligibility"]["status"] == "no" for c in r["catalogue"])  # tier-2 city
    for t in rec["tiers"].values():
        assert t["quote"]["totals"]["monthly_total"] > 0


def test_dynamic_quote_recalculation_and_validation(client, journey):
    jid = journey["id"]
    base = {"journey_id": jid, "term_months": 12, "items": [{"product_id": "P02", "quantity": 1}, {"product_id": "P07", "quantity": 3}]}
    q12 = client.post("/api/quotes/preview", json=base).json()
    q24 = client.post("/api/quotes/preview", json={**base, "term_months": 24}).json()
    assert q12["valid"] and q24["valid"]
    assert q24["quote"]["totals"]["monthly_total"] < q12["quote"]["totals"]["monthly_total"]
    # CCTV without a broadband product -> dependency error with concrete fixes
    bad = client.post("/api/quotes/preview", json={**base, "items": [{"product_id": "P23", "quantity": 2}, {"product_id": "P07", "quantity": 1}]}).json()
    assert not bad["valid"] and bad["errors"][0]["code"] == "dependency" and bad["fixes"][0]["add_one_of"]
    # tier-2 city cannot buy the 1 Gbps product
    inel = client.post("/api/quotes/preview", json={**base, "items": [{"product_id": "P03", "quantity": 1}]}).json()
    assert not inel["valid"] and inel["errors"][0]["code"] == "ineligible"
    assert client.post("/api/quotes/preview", json={**base, "items": [{"product_id": "P01", "quantity": 0}]}).status_code == 422
    assert client.post("/api/quotes/preview", json={**base, "journey_id": "nope"}).status_code == 404


def test_save_selection_blocks_invalid_and_quote_requires_selection(client):
    j = client.post("/api/journeys", json={**PROFILE, "business_name": "Fresh Co"}).json()
    assert client.post(f"/api/journeys/{j['id']}/quote").status_code == 409
    bad = client.put(f"/api/journeys/{j['id']}/selection", json={"items": [{"product_id": "P10", "quantity": 1}], "term_months": 24}).json()
    assert not bad["valid"]
    assert client.post(f"/api/journeys/{j['id']}/quote").status_code == 409  # invalid selection was not saved


@pytest.fixture(scope="module")
def order(client, journey):
    jid = journey["id"]
    sel = {"items": [{"product_id": "P02", "quantity": 1}, {"product_id": "P07", "quantity": 3}, {"product_id": "P23", "quantity": 4}], "term_months": 12}
    assert client.put(f"/api/journeys/{jid}/selection", json=sel).json()["valid"]
    quote = client.post(f"/api/journeys/{jid}/quote")
    assert quote.status_code == 201
    qid = quote.json()["id"]
    assert client.post("/api/orders", json={"quote_id": qid, "accept_terms": True}).status_code == 401  # must sign in
    h = auth(client)
    assert client.post("/api/orders", json={"quote_id": qid, "accept_terms": False}, headers=h).status_code == 422
    o = client.post("/api/orders", json={"quote_id": qid, "accept_terms": True}, headers=h)
    assert o.status_code == 201, o.text
    return {"id": o.json()["id"], "h": h, "quote": quote.json(), "journey": jid}


def test_order_created_with_unique_id_and_tracker(client, order):
    o = client.get(f"/api/orders/{order['id']}", headers=order["h"]).json()
    assert o["id"].startswith("UD-20260715-") and len(o["id"]) == 18
    assert o["status"] == "placed" and o["payment_status"] == "pending" and o["kyc_status"] == "not_started"
    assert o["totals"]["monthly_total"] == order["quote"]["totals"]["monthly_total"]
    assert o["tracker"]["next_action"]["type"] == "pay"
    again = client.post("/api/orders", json={"quote_id": order["quote"]["id"], "accept_terms": True}, headers=order["h"]).json()
    assert again["id"] == o["id"]  # idempotent per quote


def test_other_customers_cannot_see_the_order(client, order):
    other = auth(client, "intruder@example.com", "Intruder")
    assert client.get(f"/api/orders/{order['id']}", headers=other).status_code == 404
    assert client.get(f"/api/orders/{order['id']}/kyc", headers=other).status_code == 404
    assert client.get("/api/orders", headers=other).json() == []
    assert client.get("/api/admin/overview", headers=other).status_code == 403
    assert client.get("/api/admin/overview").status_code == 401


def test_payment_simulation_failure_then_success(client, order):
    h, oid = order["h"], order["id"]
    assert client.post(f"/api/orders/{oid}/schedule", json={"date": "2026-07-25", "window": "morning"}, headers=h).status_code == 409
    f = client.post(f"/api/orders/{oid}/pay", json={"method": "upi", "simulate": "fail"}, headers=h).json()
    assert f["payment_status"] == "failed"
    p = client.post(f"/api/orders/{oid}/pay", json={"method": "upi"}, headers=h).json()
    assert p["payment_status"] == "paid"
    assert client.post(f"/api/orders/{oid}/pay", json={"method": "upi"}, headers=h).status_code == 409


def test_kyc_requires_consent_before_upload(client, order):
    h, oid = order["h"], order["id"]
    f = DOCS / "K03_gst_certificate.png"
    r = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "gst_certificate"}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h)
    assert r.status_code == 422 and "consent" in r.json()["detail"].lower()
    assert client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": False}, headers=h).status_code == 422
    assert client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True, "gstin": "BADGSTIN"}, headers=h).status_code == 422
    ok = client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True, "gstin": "27XUIXG0767D1ZP", "udyam_number": "UDYAM-MH-00-9516696"}, headers=h)
    assert ok.status_code == 200 and ok.json()["consent"]["retention_days"] == 30
    assert ok.json()["declared"]["gstin"] != "27XUIXG0767D1ZP"  # masked in responses


def test_kyc_upload_validation(client, order):
    h, oid = order["h"], order["id"]
    bad = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "gst_certificate"}, files={"file": ("x.png", b"not an image", "image/png")}, headers=h)
    assert bad.status_code == 422
    unk = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "passport"}, files={"file": ("x.png", (DOCS / "K03_signatory_id.png").read_bytes(), "image/png")}, headers=h)
    assert unk.status_code == 422
    big = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "gst_certificate"}, files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * (9 * 1024 * 1024), "image/png")}, headers=h)
    assert big.status_code == 422


def test_kyc_wrong_document_type_is_flagged_then_fixed(client, order):
    h, oid = order["h"], order["id"]
    wrong = DOCS / "K03_signatory_id.png"
    r = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "gst_certificate"}, files={"file": (wrong.name, wrong.read_bytes(), "image/png")}, headers=h).json()
    assert any(i["code"] == "wrong_document_type" for i in r["result"]["issues"])
    assert r["result"]["status"] != "verified"


def test_full_kyc_verifies_and_unlocks_scheduling(client, order):
    h, oid = order["h"], order["id"]
    last = None
    for d in ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof"):
        f = DOCS / f"K03_{d}.png"
        r = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": d}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h)
        assert r.status_code == 200, r.text
        last = r.json()
    assert last["status"] == "verified", last["result"]["issues"]
    assert last["result"]["registry"]["gstin"]["status"] == "Active"
    assert "27XUIXG0767D1ZP" not in str(last)
    o = client.get(f"/api/orders/{oid}", headers=h).json()
    assert o["kyc_status"] == "verified" and o["status"] == "kyc_verified"
    assert o["tracker"]["next_action"]["type"] == "schedule"


def test_schedule_installation_and_activation(client, order):
    h, oid = order["h"], order["id"]
    slots = client.get(f"/api/orders/{oid}/slots", headers=h).json()["slots"]
    assert slots and all(s["weekday"] != "Sunday" for s in slots)
    assert client.post(f"/api/orders/{oid}/schedule", json={"date": "2026-07-15", "window": "morning"}, headers=h).status_code == 409  # not an offered slot
    day = slots[0]["date"]
    s = client.post(f"/api/orders/{oid}/schedule", json={"date": day, "window": "afternoon"}, headers=h)
    assert s.status_code == 200 and s.json()["status"] == "install_scheduled"
    assert s.json()["expected_activation"] > day
    # customers cannot activate their own order; admin can, in order
    assert client.post(f"/api/admin/orders/{oid}/advance", json={"to": "activated"}, headers=h).status_code == 403
    ah = admin_headers(client)
    assert client.post(f"/api/admin/orders/{oid}/advance", json={"to": "activated"}, headers=ah).status_code == 409
    assert client.post(f"/api/admin/orders/{oid}/advance", json={"to": "installing"}, headers=ah).status_code == 200
    done = client.post(f"/api/admin/orders/{oid}/advance", json={"to": "activated"}, headers=ah).json()
    assert done["status"] == "activated" and done["activated_on"] == "2026-07-15"
    steps = {s["key"]: s["state"] for s in done["tracker"]["steps"]}
    assert set(steps.values()) == {"done"}
    assert [e["status"] for e in done["events"]][0] == "placed"


def test_erasure_removes_documents(client, order):
    h, oid = order["h"], order["id"]
    r = client.delete(f"/api/orders/{oid}/kyc", headers=h).json()
    assert r["erased_documents"] == 4
    kyc = client.get(f"/api/orders/{oid}/kyc", headers=h).json()
    assert kyc["uploaded"] == {} and kyc["result"] is None


def test_admin_dashboards(client):
    ah = admin_headers(client)
    ov = client.get("/api/admin/overview", headers=ah).json()
    assert ov["historical"]["leads"] == 5000 and ov["historical"]["activated"] == 368
    assert ov["live"]["orders"] >= 1
    f = client.get("/api/admin/funnel", headers=ah).json()["funnel"]
    assert [s["count"] for s in f] == [5000, 3406, 1974, 861, 588, 368]
    seg = client.get("/api/admin/segments", headers=ah).json()["segments"]
    assert {s["key"] for s in seg} == {"Micro retail & services", "Professional offices", "Small multi-site businesses", "Small manufacturers"}
    leads = client.get("/api/admin/leads?size=5&segment=Professional offices", headers=ah).json()
    assert leads["total"] == 1247 and len(leads["items"]) == 5
    assert client.get("/api/admin/propensity", headers=ah).json()["auc_holdout"] > 0.6
    assert client.get("/api/admin/breakdown/nonsense", headers=ah).status_code == 404
    assert isinstance(client.get("/api/admin/advisor-leads", headers=ah).json(), list)


def test_mock_registry_lookups(client):
    h = auth(client)
    g = client.get("/api/registry/gstin/37IHKXV5167L1ZS", headers=h).json()
    assert g["found"] and g["status"] == "Cancelled"
    assert client.get("/api/registry/gstin/27XUIXG0767D1ZQ").json()["checksum_valid"] is False
    assert client.get("/api/registry/udyam/UDYAM-MH-00-9516696").json()["found"]
    assert client.get("/api/registry/udyam/UDYAM-MH-00-0000000").json()["found"] is False


def test_hindi_journey_greeting(client):
    j = client.post("/api/journeys", json={**PROFILE, "language": "hi", "business_name": "हिंदी कंपनी"}).json()
    s = client.post(f"/api/journeys/{j['id']}/advisor/start").json()
    assert "नमस्ते" in s["messages"][0]["content"]


def _order_for(client, email, name, sel_items, headers=None):
    j = client.post("/api/journeys", json={**PROFILE, "business_name": name}).json()
    assert client.put(f"/api/journeys/{j['id']}/selection", json={"items": sel_items, "term_months": 12}).json()["valid"]
    q = client.post(f"/api/journeys/{j['id']}/quote").json()
    h = headers or auth(client, email, name)
    o = client.post("/api/orders", json={"quote_id": q["id"], "accept_terms": True}, headers=h).json()
    assert client.post(f"/api/orders/{o['id']}/pay", json={"method": "card"}, headers=h).json()["payment_status"] == "paid"
    return o["id"], h


def _upload_set(client, oid, h, applicant):
    for d in ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof"):
        f = DOCS / f"{applicant}_{d}.png"
        r = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": d}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h)
        assert r.status_code == 200, r.text
    return r.json()


def test_manual_review_path_blocks_scheduling_until_admin_approves(client):
    oid, h = _order_for(client, "review@example.com", "Neelgiri Physio Clinic", [{"product_id": "P01", "quantity": 1}])
    assert client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True}, headers=h).status_code == 200
    res = _upload_set(client, oid, h, "K07")
    assert res["status"] == "needs_review"
    o = client.get(f"/api/orders/{oid}", headers=h).json()
    assert o["status"] == "placed" and o["tracker"]["next_action"]["type"] == "wait"
    sched = client.post(f"/api/orders/{oid}/schedule", json={"date": "2026-07-25", "window": "morning"}, headers=h)
    assert sched.status_code == 409 and sched.json()["detail"]["code"] == "kyc_required"
    ah = admin_headers(client)
    assert any(k["order_id"] == oid and k["status"] == "needs_review" for k in client.get("/api/admin/kyc", headers=ah).json())
    assert client.post(f"/api/admin/kyc/{oid}/decision", json={"approve": True}, headers=h).status_code == 403
    d = client.post(f"/api/admin/kyc/{oid}/decision", json={"approve": True, "note": "Name change letter seen"}, headers=ah)
    assert d.status_code == 200 and d.json()["kyc_status"] == "approved"
    o = client.get(f"/api/orders/{oid}", headers=h).json()
    assert o["status"] == "kyc_verified" and o["tracker"]["next_action"]["type"] == "schedule"
    day = client.get(f"/api/orders/{oid}/slots", headers=h).json()["slots"][0]["date"]
    assert client.post(f"/api/orders/{oid}/schedule", json={"date": day, "window": "morning"}, headers=h).status_code == 200
    # decisions only apply to cases waiting for review
    assert client.post(f"/api/admin/kyc/{oid}/decision", json={"approve": False}, headers=ah).status_code == 409


def test_rejected_identity_never_unlocks_scheduling(client):
    oid, h = _order_for(client, "rejected@example.com", "Vindhya Tours & Travels", [{"product_id": "P01", "quantity": 1}])
    client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True}, headers=h)
    res = _upload_set(client, oid, h, "K01")
    assert res["status"] == "rejected"
    assert {i["code"] for i in res["result"]["issues"]} >= {"gstin_cancelled"}
    assert client.get(f"/api/orders/{oid}", headers=h).json()["status"] == "placed"
    assert client.post(f"/api/orders/{oid}/schedule", json={"date": "2026-07-25", "window": "morning"}, headers=h).status_code == 409


def test_replacing_a_failing_document_reverifies_the_case(client):
    oid, h = _order_for(client, "fixit@example.com", "Trinity Bake House Pvt Ltd", [{"product_id": "P01", "quantity": 1}])
    client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True}, headers=h)
    res = _upload_set(client, oid, h, "K11")
    assert res["status"] == "action_required" and res["result"]["document_status"]["address_proof"] == "failed"
    f = DOCS / "K10_address_proof.png"  # a recent bill (for a different business) - still flagged, but as a name/address mismatch, not as stale
    r = client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "address_proof"}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h).json()
    codes = {i["code"] for i in r["result"]["issues"]}
    assert "address_proof_stale" not in codes and r["status"] != "verified"


def test_retention_purge_removes_expired_files(client, db):
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from app.models import KycDocument
    from app.services.kyc.service import purge_expired

    oid, h = _order_for(client, "purge@example.com", "Ganesh Woodcraft", [{"product_id": "P01", "quantity": 1}])
    client.post(f"/api/orders/{oid}/kyc/consent", json={"accepted": True}, headers=h)
    f = DOCS / "K03_signatory_id.png"
    client.post(f"/api/orders/{oid}/kyc/documents", data={"doc_type": "signatory_id"}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h)
    doc = db.query(KycDocument).order_by(KycDocument.uploaded_at.desc()).first()
    path = Path(doc.file_path)
    assert path.exists() and path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"  # stored encrypted, not as a PNG
    doc.purge_after = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert purge_expired(db) >= 1
    db.refresh(doc)
    assert doc.file_path is None and not path.exists() and doc.extracted == {}


# ------------------------------------------------------------------ Google sign-in (token verification is mocked)

def test_google_sign_in_disabled_without_client_id(client):
    assert client.get("/api/auth/config").json() == {"google_client_id": None}
    r = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 401 and "not configured" in r.json()["detail"]


def _mock_google(monkeypatch, payload=None, status=200):
    import httpx

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "client-123.apps.googleusercontent.com")

    class R:
        status_code = status

        def json(self):
            return payload

    monkeypatch.setattr(httpx, "get", lambda *a, **k: R())


GOOD = {"aud": "client-123.apps.googleusercontent.com", "iss": "https://accounts.google.com", "email": "Priya@Gmail.com", "email_verified": "true", "name": "Priya Nair", "sub": "1"}


def test_google_sign_up_then_sign_in_reuses_account(client, monkeypatch):
    _mock_google(monkeypatch, GOOD)
    assert client.get("/api/auth/config").json()["google_client_id"].startswith("client-123")
    first = client.post("/api/auth/google", json={"credential": "x" * 40}).json()
    assert first["created"] is True and first["user"]["email"] == "priya@gmail.com" and first["user"]["role"] == "customer"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {first['token']}"}).json()
    assert me["name"] == "Priya Nair"
    second = client.post("/api/auth/google", json={"credential": "y" * 40}).json()
    assert second["created"] is False and second["user"]["id"] == first["user"]["id"]
    # the random password hash cannot be used to log in with a guessed password
    assert client.post("/api/auth/login", json={"email": "priya@gmail.com", "password": "password123"}).status_code == 401


def test_google_rejects_wrong_audience_unverified_email_and_bad_token(client, monkeypatch):
    for bad, status in [({**GOOD, "aud": "someone-else"}, 200), ({**GOOD, "email_verified": "false"}, 200), ({**GOOD, "iss": "evil.example"}, 200), ({"error": "invalid_token"}, 400)]:
        _mock_google(monkeypatch, bad, status)
        r = client.post("/api/auth/google", json={"credential": "z" * 40})
        assert r.status_code == 401, bad
    assert client.post("/api/auth/google", json={"credential": "short"}).status_code == 422


def test_google_links_to_existing_password_account(client, monkeypatch):
    client.post("/api/auth/register", json={"email": "linked@example.com", "name": "Linked", "password": "Passw0rd!x"})
    _mock_google(monkeypatch, {**GOOD, "email": "linked@example.com"})
    r = client.post("/api/auth/google", json={"credential": "q" * 40}).json()
    assert r["created"] is False and r["user"]["email"] == "linked@example.com"
