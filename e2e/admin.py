"""Browser smoke test of the admin dashboard: every tab renders data without errors."""
import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://localhost:3000")
ap.add_argument("--shots", default="")
ap.add_argument("--email", default="admin@accel.example")
ap.add_argument("--password", default="ChangeMe!123")
a = ap.parse_args()
shots = Path(a.shots) if a.shots else None
if shots:
    shots.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    pg.goto(f"{a.base}/admin")
    expect(pg.get_by_text("Admin access only")).to_be_visible()  # guard works when signed out
    pg.goto(f"{a.base}/login?next=/admin")
    pg.get_by_label("Email").fill(a.email)
    pg.get_by_label("Password").fill(a.password)
    pg.get_by_role("button", name="Sign in").click()
    pg.wait_for_url("**/admin")
    expect(pg.get_by_text("Apr-Jun 2026 baseline")).to_be_visible()
    pg.wait_for_selector(".recharts-surface")
    if shots:
        pg.screenshot(path=str(shots / "admin_overview.png"), full_page=True)
    for tab, probe in [("Segments", "Professional offices"), ("Leads", "Propensity"), ("Orders", re.compile(r"UD-\d{8}")), ("KYC queue", re.compile("Verified|Needs|Incomplete|Action", re.I)), ("Advisor leads", re.compile("Business|No unclosed"))]:
        pg.get_by_role("tab", name=tab, exact=True).click()
        expect(pg.get_by_text(probe).first).to_be_visible(timeout=15000)
        if shots:
            pg.screenshot(path=str(shots / f"admin_{tab.split()[0].lower()}.png"), full_page=True)
    b.close()
if errs:
    print("ERRORS:", *errs, sep="\n  ")
    sys.exit(1)
print("ADMIN OK")
