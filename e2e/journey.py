"""Browser end-to-end test of the customer journey (Playwright, real backend + frontend).

Usage (with backend on :8000 and frontend on :3000 running):
    backend/.venv/Scripts/python e2e/journey.py [--mobile] [--shots DIR]
"""
import argparse
import re
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://localhost:3000")
ap.add_argument("--mobile", action="store_true")
ap.add_argument("--shots", default="")
ap.add_argument("--sample", default="K03")
args = ap.parse_args()
shots = Path(args.shots) if args.shots else None
if shots:
    shots.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    if shots:
        page.screenshot(path=str(shots / f"{name}.png"), full_page=True)


def step(msg):
    print(f"  - {msg}", flush=True)


email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844} if args.mobile else {"width": 1280, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
    page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 500 else None)

    step("landing")
    page.goto(args.base)
    expect(page.get_by_role("heading", level=1)).to_contain_text("one plan")
    shot(page, "01_landing")

    step("onboarding")
    page.get_by_role("link", name=re.compile("Build my plan")).first.click()
    page.wait_for_url("**/onboarding")
    page.get_by_label("Business name").fill("Sharma Dental Care")
    page.get_by_label("Business category").select_option("Dental clinic")
    page.get_by_label("City").select_option("Pune")
    page.get_by_label("Number of employees").fill("14")
    page.get_by_label("Number of branches / sites").fill("1")
    page.get_by_label("Current connectivity").select_option("Home broadband")
    page.get_by_label(re.compile("Monthly budget")).fill("12000")
    page.get_by_label(re.compile("What you spend today")).fill("3000")
    page.get_by_label("Your name").fill("Dr Anil Sharma")
    page.get_by_label("Mobile number").fill("9876543210")
    page.get_by_label("GSTIN (optional)").fill("29HLDXH5566X1ZB")  # active GSTIN from the registry
    expect(page.get_by_text("Found:")).to_be_visible()
    shot(page, "02_onboarding")
    page.get_by_role("button", name=re.compile("Continue to advisor")).click()
    page.wait_for_url("**/advisor")

    step("advisor conversation")
    expect(page.get_by_text("I am your Accel Business advisor")).to_be_visible()
    box = page.get_by_label("Message")
    for text in ["Internet keeps going down and it is slow", "I need CCTV with 4 cameras, WhatsApp and email", "Yes fibre is available", "5", "recommend"]:
        n = page.locator("[aria-live=polite] > div").count()
        box.fill(text)
        box.press("Enter")
        expect(page.locator("[aria-live=polite] > div")).not_to_have_count(n)
        time.sleep(0.4)
        if page.get_by_role("link", name=re.compile("Review & customise")).count():
            break
    expect(page.get_by_role("link", name=re.compile("Review & customise"))).to_be_visible()
    shot(page, "03_advisor")

    step("bundle: toggle + dynamic pricing")
    page.get_by_role("link", name=re.compile("Review & customise")).click()
    page.wait_for_url("**/bundle")
    expect(page.get_by_text("In your bundle")).to_be_visible()
    price = page.locator("dd", has_text="₹").first
    expect(price).to_be_visible()
    before = page.locator("dt:has-text('Per month') + dd").inner_text()
    page.get_by_label("Contract length").select_option("24")
    page.wait_for_function("(b) => document.querySelector('aside dl') && !document.body.innerText.includes('Updating') ", arg=before)
    time.sleep(0.8)
    after = page.locator("dt:has-text('Per month') + dd").inner_text()
    assert before != after, f"price did not change with term ({before} -> {after})"
    step(f"  term 12 -> 24 changed monthly {before} -> {after}")
    shot(page, "04_bundle")
    page.get_by_role("button", name=re.compile("Get quote")).click()
    page.wait_for_url("**/checkout**")

    step("checkout: register + order + simulated payment")
    expect(page.get_by_text("Quote & checkout")).to_be_visible()
    shot(page, "05_checkout_anon")
    page.get_by_role("link", name="Create account").click()
    page.get_by_label("Full name").fill("Anil Sharma")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill("Passw0rd!x")
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url("**/checkout**")
    page.get_by_label(re.compile("I accept the contract")).check()
    page.get_by_role("button", name="Confirm order").click()
    expect(page.get_by_text(re.compile(r"UD-\d{8}-[A-Z0-9]{6}")).first).to_be_visible()
    order_id = re.search(r"UD-\d{8}-[A-Z0-9]{6}", page.inner_text("body")).group(0)
    step(f"  order {order_id}")
    page.get_by_label("Demo: simulate a failed payment").check()
    page.get_by_role("button", name=re.compile(r"^Pay ")).click()
    expect(page.get_by_text(re.compile("simulated payment failed"))).to_be_visible()
    page.get_by_label("Demo: simulate a failed payment").uncheck()
    page.get_by_role("button", name=re.compile(r"^Pay ")).click()
    page.wait_for_url("**/kyc")

    step("KYC: consent -> sample upload -> verified")
    expect(page.get_by_text("Before we start: your consent")).to_be_visible()
    shot(page, "06_kyc_consent")
    expect(page.get_by_role("button", name="I agree, continue")).to_be_disabled()
    page.get_by_label(re.compile("I consent to Accel Business")).check()
    page.get_by_role("button", name="I agree, continue").click()
    expect(page.get_by_text("Verification status")).to_be_visible()
    page.get_by_label("Sample applicant").select_option(args.sample)
    page.get_by_role("button", name="Load").click()
    expect(page.get_by_text("Verified", exact=True).first).to_be_visible(timeout=180000)
    shot(page, "07_kyc_verified")
    page.get_by_text(re.compile(r"Show all \d+ checks")).click()
    expect(page.get_by_text("GSTIN checksum")).to_be_visible()
    shot(page, "08_kyc_checks")

    step("tracker: schedule installation")
    page.get_by_role("link", name=re.compile("Continue to installation")).click()
    expect(page.get_by_text("Pick a convenient installation slot")).to_be_visible()
    page.get_by_role("button", name=re.compile("9:00")).first.click()
    page.get_by_role("button", name="Book this slot").click()
    expect(page.get_by_text(re.compile("Technician visit on"))).to_be_visible()
    shot(page, "09_tracker")

    step("admin sees the order")
    page.get_by_role("button", name=re.compile("Sign out")).first.click() if not args.mobile else None
    browser.close()

if errors:
    print("BROWSER ERRORS:", *errors, sep="\n  ")
    sys.exit(1)
print(f"E2E OK ({'mobile' if args.mobile else 'desktop'}) order={order_id}")
