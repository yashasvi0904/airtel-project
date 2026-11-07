"""python e2e/language_audit.py [out_dir] [hi,ta,...]  (both servers up)
Every customer page x every language on an emulated phone: overflow, leaked {placeholders}, residual English, page errors."""
import json
import re
import sys
from pathlib import Path
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

API, WEB = "http://localhost:8000/api", "http://localhost:3000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/lang"
Path(OUT).mkdir(parents=True, exist_ok=True)
LANGS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["hi", "mr", "kn", "gu", "te", "ta", "bn", "pa", "ml"]
PROFILE = {"business_name": "Ganesh Woodcraft", "business_type": "Furniture workshop", "city": "Nagpur", "employees": 12, "sites": 1,
           "current_internet": "Home broadband", "monthly_budget": 15000, "monthly_telecom_spend": 3000, "has_gstin": True,
           "gstin": "27XUIXG0767D1ZP", "has_udyam": True, "contact_name": "Joseph Singh", "phone": "9876543210", "language": "en"}
# words that legitimately stay Latin: brands, units, abbreviations, product names, proper nouns from the data
ALLOW = set("""accel business udyam digital airtel whatsapp upi gst gstin kyc otp sim sims cctv pos wi fi sd wan ivr sms ai ip iot mbps gbps gb tb
 biz fibre airfiber leased line postpaid cloud email office suite endpoint security managed firewall secure guest network website domain starter
 telephony toll free backup failover static fleet tracker machine monitoring billing api synthetic gemini claude sandbox nagpur ganesh woodcraft
 joseph singh furniture workshop pdf png jpg mb id udyog hdfc sbi icici axis bank kotak punjab baroda yes idfc first indusind canara union india
 mastercard visa rupay amex card net txt tier slas sla dlt ok qr mm yy cvv gstin udyam eg e.g ravi okhdfc""".split())

def call(path, body=None, token=None, method=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.load(urllib.request.urlopen(req))

tag = uuid.uuid4().hex[:8]
tok = call("/auth/register", {"email": f"lang{tag}@example.com", "name": "Lang User", "password": "Passw0rd!x", "phone": "9876543210"})["token"]


def setup(lang):
    j = call("/journeys", {**PROFILE, "language": lang, "business_name": "Ganesh Woodcraft"}, token=tok)
    call(f"/journeys/{j['id']}/advisor/start", {}, token=tok)
    call(f"/journeys/{j['id']}/advisor/message", {"text": "I need 3 cameras and whatsapp, recommend"}, token=tok)
    q = call(f"/journeys/{j['id']}/quote", {}, token=tok)
    oid = call("/orders", {"quote_id": q["id"], "accept_terms": True}, token=tok)["id"]
    pages = [("home", "/"), ("onboarding", "/onboarding"), ("advisor", "/advisor"), ("bundle", "/bundle"), ("checkout", f"/checkout?quote={q['id']}"),
             ("orders", "/orders"), ("order", f"/orders/{oid}"), ("pay", f"/orders/{oid}/pay"), ("kyc", f"/orders/{oid}/kyc"), ("login", "/login")]
    return j, pages


LATIN = re.compile(r"[A-Za-z][A-Za-z'’.]{3,}")

with sync_playwright() as p:
    b = p.chromium.launch()
    summary = {}
    for lang in LANGS:
        j, PAGES = setup(lang)
        ctx = b.new_context(**p.devices["Pixel 7"])
        ctx.add_init_script(f"localStorage.setItem('udyam.token','{tok}');localStorage.setItem('udyam.journey','{j['id']}');localStorage.setItem('udyam.lang','{lang}')")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        rows = []
        for name, path in PAGES:
            pg.goto(WEB + path)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(1500)
            info = pg.evaluate("""() => {
              const t = document.body.innerText;
              const sw = screen.width, clip = [];
              const scrollable = el => { for (let a = el.parentElement; a; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
              document.querySelectorAll('body *').forEach(e => { const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
                if (r.width > 0 && r.right > sw + 2 && st.position !== 'fixed' && st.display !== 'none' && !scrollable(e)) clip.push(e.tagName + '.' + (e.className || '').toString().slice(0, 30) + '@' + Math.round(r.right)); });
              return {clip: clip.slice(0, 3), text: t, over: document.documentElement.scrollWidth - screen.width, lang: document.documentElement.lang,
                      braces: (t.match(/\\{\\w+\\}/g) || []).slice(0, 3)};
            }""")
            words = [w.strip(".'’").lower() for w in LATIN.findall(info["text"])]
            eng = [w for w in words if w not in ALLOW and not w.startswith(("http",))]
            rows.append((name, info["over"] + (1000 if info["clip"] else 0), info["braces"] or info["clip"], len(eng), len(words), sorted(set(eng))[:10], info["lang"]))
            if name in ("advisor", "bundle", "pay") and lang in ("ta", "ml", "hi", "bn"):
                pg.screenshot(path=f"{OUT}/{lang}_{name}.png", full_page=True)
        summary[lang] = rows
        print(f"== {lang}  (html lang={rows[0][6]})  page errors: {errs or 'none'}")
        for r in rows:
            flag = "  <-- CHECK" if r[1] > 0 or r[2] or r[3] > 25 else ""
            print(f"   {r[0]:11} overflow={r[1]:>3} braces={r[2] or '-'}  latin-words: {r[3]:>3} not-allowed  {r[5][:6] if r[3] else ''}{flag}")
        ctx.close()
    b.close()
