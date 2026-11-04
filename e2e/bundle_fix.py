"""Browser check: removing the connectivity product that CCTV depends on shows the fix card; one click repairs it."""
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
profile = {"business_name": "Fix Test Clinic", "business_type": "Dental clinic", "city": "Pune", "employees": 14, "sites": 1,
           "current_internet": "Home broadband", "monthly_budget": 20000, "has_gstin": False, "has_udyam": False, "language": "en"}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    jid = pg.request.post(f"{BASE}/api/journeys", data=profile).json()["id"]
    pg.request.post(f"{BASE}/api/journeys/{jid}/advisor/start")
    pg.request.post(f"{BASE}/api/journeys/{jid}/advisor/message", data={"text": "I want CCTV with 4 cameras"})
    pg.request.post(f"{BASE}/api/journeys/{jid}/advisor/message", data={"text": "recommend"})
    pg.goto(BASE)
    pg.evaluate(f"localStorage.setItem('udyam.journey', '{jid}')")
    pg.goto(f"{BASE}/bundle")
    expect(pg.get_by_text("Cloud CCTV").first).to_be_visible()
    fibre = pg.locator("li", has_text=re.compile("Biz Fibre")).first
    fibre.get_by_role("button", name="Remove").click()
    expect(pg.get_by_text("Some products depend on others")).to_be_visible()
    expect(pg.get_by_role("button", name="Get quote & checkout")).to_be_disabled()
    pg.get_by_role("button", name=re.compile(r"^Add .*(Fibre|AirFiber|Leased)")).first.click()
    expect(pg.get_by_text("Some products depend on others")).to_have_count(0)
    expect(pg.get_by_role("button", name="Get quote & checkout")).to_be_enabled()
    # GSTIN-only product explains itself and unlocks after GSTIN verification
    pg.get_by_role("button", name=re.compile("Browse all other products")).click()
    expect(pg.get_by_text("Unlock GSTIN-only products")).to_be_visible()
    pg.get_by_label("GSTIN", exact=True).fill("29HLDXH5566X1ZB")
    pg.get_by_role("button", name="Verify").click()
    expect(pg.get_by_text("GSTIN verified")).to_be_visible()
    b.close()
if errs:
    print("ERRORS", errs)
    sys.exit(1)
print("BUNDLE FIX OK")
