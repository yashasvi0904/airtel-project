"""A whole purchase done by a Hindi-speaking owner on an emulated phone: first visit in a Hindi browser -> language auto-detected ->
onboarding -> advisor (typing Hindi) -> bundle -> checkout -> UPI payment -> KYC page. Labels are looked up from the real Hindi
dictionary, so this fails if a button the customer needs is not translated."""
import json
import re
import sys
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = "http://localhost:3000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/hindi"
Path(OUT).mkdir(parents=True, exist_ok=True)
HI = json.loads((Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "locales" / "hi.json").read_text(encoding="utf-8"))
t = lambda s: HI[s]
problems = []


def step(m):
    print("  -", m)


with sync_playwright() as p:
    b = p.chromium.launch()
    # a phone whose language list says Hindi: nobody has to find a language switch
    ctx = b.new_context(**p.devices["Pixel 7"], locale="hi-IN")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: problems.append(str(e)[:150]))
    pg.on("console", lambda m: problems.append(m.text[:150]) if m.type == "error" and "422" not in m.text and "favicon" not in m.text else None)

    pg.goto(WEB)
    expect(pg.locator("h1")).to_contain_text("इंटरनेट", timeout=20000)
    assert pg.evaluate("document.documentElement.lang") == "hi"
    step("first visit in a Hindi browser opens in Hindi (auto-detected)")
    pg.screenshot(path=f"{OUT}/hi_01_home.png")

    pg.get_by_role("link", name=re.compile(re.escape(t("Build my plan")))).first.click()
    pg.wait_for_url("**/onboarding")
    expect(pg.get_by_text(t("Tell us about your business")).first).to_be_visible()
    pg.fill("#bn", "शर्मा किराना स्टोर")
    pg.select_option("#bt", index=1)
    pg.select_option("#city", "Nagpur")
    pg.fill("#emp", "6")
    pg.fill("#ph", "9876543210")
    pg.screenshot(path=f"{OUT}/hi_02_onboarding.png")
    pg.get_by_role("button", name=re.compile(re.escape(t("Continue to advisor")))).click()
    pg.wait_for_url("**/advisor", timeout=20000)
    step("onboarding in Hindi -> advisor")

    # the advisor greets in Hindi and asks its first question in Hindi (server-side language = hi)
    expect(pg.get_by_text(re.compile("नमस्ते"))).to_be_visible(timeout=20000)
    box = pg.get_by_label(t("Message"))
    box.fill("मुझे 3 कैमरे और व्हाट्सऐप चाहिए, सुझाव दीजिए")
    pg.get_by_role("button", name=t("Send")).click()
    expect(pg.get_by_text(re.compile(r"₹[\d,]+")).first).to_be_visible(timeout=60000)
    pg.screenshot(path=f"{OUT}/hi_03_advisor.png")
    step("typed Hindi, got a Hindi recommendation with prices")

    # recommendation ready -> sticky call to action on the phone
    cta = pg.get_by_role("link", name=re.compile(re.escape(t("Review & customise bundle")))).last
    expect(cta).to_be_visible(timeout=20000)
    cta.click()
    pg.wait_for_url("**/bundle")
    expect(pg.get_by_text(t("Your price"))).to_be_visible(timeout=20000)
    pg.screenshot(path=f"{OUT}/hi_04_bundle.png")
    step("bundle page in Hindi")

    pg.get_by_role("button", name=re.compile(re.escape(t("Get quote & checkout")))).last.click()
    pg.wait_for_url("**/checkout**", timeout=20000)
    expect(pg.get_by_text(t("Quote & checkout"))).to_be_visible()
    email = f"hi{uuid.uuid4().hex[:8]}@example.com"
    pg.get_by_role("link", name=t("Create account")).click()
    pg.get_by_label(t("Full name")).fill("राजेश शर्मा")
    pg.get_by_label(t("Email")).fill(email)
    pg.get_by_label(t("Password")).fill("Passw0rd!x")
    pg.get_by_role("button", name=t("Create account")).click()
    pg.wait_for_url("**/checkout**")
    pg.get_by_label(re.compile(re.escape(t("I accept the contract terms and the {n}-month commitment.").split("{n}")[0]))).check()
    pg.get_by_role("button", name=t("Confirm order")).click()
    pg.wait_for_url("**/pay", timeout=20000)
    step("checkout in Hindi -> order placed")

    expect(pg.get_by_text(t("Complete your payment"))).to_be_visible(timeout=15000)
    pg.get_by_label(t("UPI ID")).fill("rajesh@okhdfc")
    pg.get_by_role("button", name=t("Send payment request")).click()
    expect(pg.get_by_text(t("Waiting for your approval"))).to_be_visible(timeout=15000)
    pg.screenshot(path=f"{OUT}/hi_05_pay_pending.png")
    expect(pg.get_by_text(re.compile(re.escape(t("Payment received - {amount}").split("{amount}")[0])))).to_be_visible(timeout=30000)
    pg.wait_for_url("**/kyc", timeout=20000)
    expect(pg.get_by_text(t("Smart KYC"))).to_be_visible()
    pg.screenshot(path=f"{OUT}/hi_06_kyc.png")
    step("UPI payment in Hindi -> KYC")

    # switching language mid-journey keeps the page and re-renders in the new language
    pg.get_by_role("button", name=t("Choose language")).click()
    pg.get_by_role("button", name=re.compile("தமிழ்")).click()
    expect(pg.get_by_role("heading", level=1)).not_to_have_text(t("Smart KYC"), timeout=10000)
    assert pg.evaluate("document.documentElement.lang") == "ta"
    pg.screenshot(path=f"{OUT}/hi_07_switched_to_tamil.png")
    step("switched to Tamil on the same page")
    b.close()
print("\nproblems:", problems or "none")
sys.exit(1 if problems else 0)
