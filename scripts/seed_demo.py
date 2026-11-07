"""Fill a FRESH demo database with a realistic admin workload, through the public API (no database shortcuts), so the admin
dashboard has something to show: orders at every stage, KYC cases that need a human decision, and unclosed advisor leads.

  backend/.venv/Scripts/python scripts/seed_demo.py --api http://127.0.0.1:8000/api --admin-password <password>

Everything is synthetic: the KYC documents are the specimen images supplied with the dataset, customers are demo-*@example.com.
Run it once per fresh database (scripts/share_demo.ps1 does).
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "assignment" / "data" / "kyc_documents"
DOC_TYPES = ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof")
PW = "Demo#Pass-" + uuid.uuid4().hex[:8]

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://127.0.0.1:8000/api")
ap.add_argument("--admin-email", default="admin@accel.example")
ap.add_argument("--admin-password", required=True)
args = ap.parse_args()
c = httpx.Client(base_url=args.api, timeout=120)


def ok(r: httpx.Response) -> dict:
    if r.status_code >= 300:
        sys.exit(f"seed failed: {r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def profile(name: str, kind: str, city: str, employees: int, sites: int, internet: str, budget: int, gstin: str | None, contact: str, phone: str, lang: str = "en") -> dict:
    return {"business_name": name, "business_type": kind, "city": city, "employees": employees, "sites": sites, "current_internet": internet,
            "monthly_budget": budget, "monthly_telecom_spend": max(1500, budget // 4), "has_gstin": bool(gstin), "gstin": gstin or "",
            "has_udyam": True, "contact_name": contact, "phone": phone, "language": lang}


GANESH = profile("Ganesh Woodcraft", "Furniture workshop", "Nagpur", 12, 1, "Home broadband", 15000, "27XUIXG0767D1ZP", "Joseph Singh", "9000000001")


def place_order(email: str, prof: dict, items: list[dict], term: int = 12) -> tuple[str, dict]:
    tok = ok(c.post("/auth/register", json={"email": email, "name": prof["contact_name"], "password": PW, "phone": prof["phone"]}))["token"]
    j = ok(c.post("/journeys", json=prof))
    ok(c.post(f"/journeys/{j['id']}/advisor/start"))
    assert ok(c.put(f"/journeys/{j['id']}/selection", json={"items": items, "term_months": term}))["valid"], f"invalid selection for {prof['business_name']}"
    q = ok(c.post(f"/journeys/{j['id']}/quote"))
    o = ok(c.post("/orders", json={"quote_id": q["id"], "accept_terms": True}, headers=hdr(tok)))
    return o["id"], hdr(tok)


def pay(oid: str, h: dict):
    p = ok(c.post(f"/orders/{oid}/payments", json={"method": "upi", "upi": {"flow": "collect", "vpa": "ravi@okhdfc"}}, headers={**h, "Idempotency-Key": uuid.uuid4().hex}))
    for _ in range(30):  # the sandbox "bank" approves after a few seconds; polling is what settles it
        got = ok(c.get(f"/payments/{p['id']}", headers=h))
        if got["status"] == "succeeded":
            return
        time.sleep(1)
    sys.exit(f"payment for {oid} did not settle")


def kyc(oid: str, h: dict, applicant: str) -> str:
    ok(c.post(f"/orders/{oid}/kyc/consent", json={"accepted": True}, headers=h))
    res = {}
    for d in DOC_TYPES:
        f = DOCS / f"{applicant}_{d}.png"
        res = ok(c.post(f"/orders/{oid}/kyc/documents", data={"doc_type": d}, files={"file": (f.name, f.read_bytes(), "image/png")}, headers=h))
    return res["status"]


def schedule(oid: str, h: dict):
    day = ok(c.get(f"/orders/{oid}/slots", headers=h))["slots"][0]["date"]
    ok(c.post(f"/orders/{oid}/schedule", json={"date": day, "window": "morning"}, headers=h))


admin = hdr(ok(c.post("/auth/login", json={"email": args.admin_email, "password": args.admin_password}))["token"])
summary = []

# 1. Fully done: verified, scheduled, installed, ACTIVATED (the happy path to completion)
oid, h = place_order("demo-activated@example.com", GANESH, [{"product_id": "P02", "quantity": 1}, {"product_id": "P07", "quantity": 3}])
pay(oid, h); summary.append(("Ganesh Woodcraft", "KYC " + kyc(oid, h, "K03"))); schedule(oid, h)
ok(c.post(f"/admin/orders/{oid}/advance", json={"to": "installing"}, headers=admin)); ok(c.post(f"/admin/orders/{oid}/advance", json={"to": "activated"}, headers=admin))

# 2. Verified and scheduled - waiting for the admin to start the installation (demo: click "Start installation" then "Mark activated")
oid, h = place_order("demo-install@example.com", {**GANESH, "business_name": "Sharma Medical Stores", "business_type": "Pharmacy", "city": "Pune", "contact_name": "Neha Sharma", "phone": "9000000002"},
                     [{"product_id": "P01", "quantity": 1}, {"product_id": "P07", "quantity": 2}])
pay(oid, h); summary.append(("Sharma Medical Stores", "KYC " + kyc(oid, h, "K03"))); schedule(oid, h)

# 3. KYC needs a HUMAN decision (the admin's review queue): name on the GST certificate differs from the registry
oid, h = place_order("demo-review@example.com", {**GANESH, "business_name": "Neelgiri Physio Clinic", "business_type": "Physiotherapy clinic", "city": "Coimbatore", "contact_name": "Arun Kumar", "phone": "9000000003", "language": "ta"},
                     [{"product_id": "P01", "quantity": 1}])
pay(oid, h); summary.append(("Neelgiri Physio Clinic", "KYC " + kyc(oid, h, "K07")))

# 4. Rejected by the checks (GSTIN cancelled in the registry)
oid, h = place_order("demo-rejected@example.com", {**GANESH, "business_name": "Vindhya Tours & Travels", "business_type": "Travel agency", "city": "Bhopal", "contact_name": "Rahul Verma", "phone": "9000000004"},
                     [{"product_id": "P01", "quantity": 1}])
pay(oid, h); summary.append(("Vindhya Tours & Travels", "KYC " + kyc(oid, h, "K01")))

# 5. Customer must fix something (utility bill older than 90 days)
oid, h = place_order("demo-fixit@example.com", {**GANESH, "business_name": "Trinity Bake House Pvt Ltd", "business_type": "Bakery", "city": "Kochi", "contact_name": "Mary Joseph", "phone": "9000000005", "language": "ml"},
                     [{"product_id": "P01", "quantity": 1}])
pay(oid, h); summary.append(("Trinity Bake House", "KYC " + kyc(oid, h, "K11")))

# 6. Paid, has not started KYC yet (admin can see who is stuck before documents)
oid, h = place_order("demo-nokyc@example.com", {**GANESH, "business_name": "Kisan Agro Traders", "business_type": "Hardware store", "city": "Nashik", "contact_name": "Prakash Patil", "phone": "9000000006", "language": "mr"},
                     [{"product_id": "P01", "quantity": 1}])
pay(oid, h); summary.append(("Kisan Agro Traders", "paid, KYC not started"))

# 7. Placed, NOT paid yet
oid, h = place_order("demo-unpaid@example.com", {**GANESH, "business_name": "Lotus Beauty Salon", "business_type": "Salon", "city": "Jaipur", "contact_name": "Pooja Gupta", "phone": "9000000007", "language": "hi"},
                     [{"product_id": "P01", "quantity": 1}])
summary.append(("Lotus Beauty Salon", "order placed, unpaid"))

# 8. Unclosed advisor journeys -> the admin's propensity-ranked "who to call" list (no orders)
for p in [profile("Om Sai Kirana", "Kirana store", "Mysuru", 3, 1, "Mobile hotspot", 3000, None, "Suresh Naik", "9000000008", "kn"),
          profile("Dr. Iyer Dental Clinic", "Dental clinic", "Chennai", 9, 1, "Home broadband", 12000, None, "Dr. Iyer", "9000000009", "ta"),
          profile("Bhatia Auto Components", "Auto-parts unit", "Ludhiana", 45, 2, "Leased line", 60000, None, "Harpreet Bhatia", "9000000010", "pa"),
          profile("Spice Route Restaurants", "Restaurant chain", "Hyderabad", 30, 4, "Business broadband", 40000, None, "Fatima Khan", "9000000011", "te")]:
    j = ok(c.post("/journeys", json=p))
    ok(c.post(f"/journeys/{j['id']}/advisor/start"))
    summary.append((p["business_name"], "advisor lead, no order"))

print("Demo data created:")
for name, what in summary:
    print(f"  - {name}: {what}")
print("Admin: orders", len(ok(c.get("/admin/orders", headers=admin))), "| KYC cases", len(ok(c.get("/admin/kyc", headers=admin))), "| advisor leads", len(ok(c.get("/admin/advisor-leads", headers=admin))))
