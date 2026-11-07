"""Phone audit (run with both servers up): python e2e/phone_audit.py [out_dir]
Phone audit: every customer page on an emulated Android phone (touch, 393x851). Reports horizontal overflow,
small tap targets (<44px), tiny text (<12px), inputs that would pop the wrong keyboard, and writes screenshots.

Also reports CLIPPED: elements past the screen edge that are not inside a deliberately scrollable box (catches overflow-hidden hiding a too-wide layout).
Note the reference width is screen.width: an over-wide page makes mobile browsers widen the layout viewport, so comparing with window.innerWidth hides the problem."""
import json
import sys
from pathlib import Path
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

API, WEB = "http://localhost:8000/api", "http://localhost:3000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "out/phone"
Path(OUT).mkdir(parents=True, exist_ok=True)
PROFILE = {"business_name": "Ganesh Woodcraft", "business_type": "Furniture workshop", "city": "Nagpur", "employees": 12, "sites": 1,
           "current_internet": "Home broadband", "monthly_budget": 15000, "monthly_telecom_spend": 3000, "has_gstin": True,
           "gstin": "27XUIXG0767D1ZP", "has_udyam": True, "contact_name": "Joseph Singh", "phone": "9876543210", "language": "en"}


def call(path, body=None, token=None, method=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.load(urllib.request.urlopen(req))


tag = uuid.uuid4().hex[:8]
tok = call("/auth/register", {"email": f"aud{tag}@example.com", "name": "Audit User", "password": "Passw0rd!x", "phone": "9876543210"})["token"]
j = call("/journeys", PROFILE, token=tok)
call(f"/journeys/{j['id']}/advisor/start", {}, token=tok)
call(f"/journeys/{j['id']}/advisor/message", {"text": "I need 3 cameras and whatsapp, recommend"}, token=tok)
q = call(f"/journeys/{j['id']}/quote", {}, token=tok)
o = call("/orders", {"quote_id": q["id"], "accept_terms": True}, token=tok)
oid = o["id"]

PAGES = [("home", "/"), ("onboarding", "/onboarding"), ("advisor", "/advisor"), ("bundle", "/bundle"), ("checkout", f"/checkout?quote={q['id']}"),
         ("orders", "/orders"), ("order", f"/orders/{oid}"), ("pay", f"/orders/{oid}/pay"), ("kyc", f"/orders/{oid}/kyc"), ("login", "/login"), ("register", "/register")]

JS = """() => {
  const out = {overflow: document.documentElement.scrollWidth - screen.width, small: [], tiny: 0, kb: []};
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };

  const sw = screen.width; out.clip = [];
  const scrollable = el => { for (let a = el.parentElement; a; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  document.querySelectorAll('body *').forEach(e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    if (r.width > 0 && r.right > sw + 2 && s.position !== 'fixed' && !scrollable(e) && getComputedStyle(e).display !== 'none') out.clip.push(e.tagName + '.' + (e.className || '').toString().slice(0, 40) + ' right=' + Math.round(r.right)); });
  out.clip = out.clip.slice(0, 4);
  document.querySelectorAll('a,button,[role=radio],[role=button],input:not([type=hidden]),select,textarea,summary').forEach(e => {
    if (!vis(e)) return; const r = e.getBoundingClientRect();
    const isInline = e.tagName === 'A' && e.closest('p,li,span,dd,div.text-xs,div.text-sm') && e.parentElement && e.parentElement.tagName !== 'NAV' && r.height < 30;
    if ((r.height < 44 || r.width < 44) && !(e.type === 'checkbox' || e.type === 'radio')) out.small.push((e.innerText || e.getAttribute('aria-label') || e.placeholder || e.tagName).trim().slice(0, 34) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    if (e.tagName === 'INPUT' && ['text', 'search'].includes(e.type) && !e.inputMode && /phone|mobile|number|otp|pin|amount|budget|gstin|employees/i.test((e.name || '') + (e.id || '') + (e.placeholder || ''))) out.kb.push(e.id || e.name || e.placeholder);
  });
  document.querySelectorAll('body *').forEach(e => { if (e.children.length === 0 && e.textContent.trim() && vis(e) && parseFloat(getComputedStyle(e).fontSize) < 12) out.tiny++; });
  return out;
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices["Pixel 7"])
    ctx.add_init_script(f"localStorage.setItem('udyam.token', '{tok}'); localStorage.setItem('udyam.journey', '{j['id']}')")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    for name, path in PAGES:
        pg.goto(WEB + path)
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(1200)
        r = pg.evaluate(JS)
        pg.screenshot(path=f"{OUT}/{name}.png", full_page=True)
        print(f"{name:10} overflow={r['overflow']:>4}  tiny_text={r['tiny']:>3}  small_targets={len(r['small']):>2}  kb_issues={r['kb']} CLIPPED={r['clip'] or '-'}")
        for s in r["small"][:8]:
            print("            small:", s)
    print("page errors:", errs or "none")
    b.close()
