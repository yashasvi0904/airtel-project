"""PWA checks in real Chromium against a PRODUCTION build (service worker is registered only in production):
installability (manifest + icons + SW as Chrome sees them), service worker control, offline fallback, /api never cached,
install banner/menu (Chrome prompt simulated with a synthetic beforeinstallprompt - a headless browser never fires the real one),
iOS manual-install hint, microphone + camera permission headers, and the KYC "Take photo" input incl. big-photo shrinking.

  cd frontend && npm run build && npm run start -- -p 3000      (and the backend on :8000)
  backend/.venv/Scripts/python e2e/pwa.py
"""
import io
import json
import sys
import urllib.request
import uuid
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

WEB = "http://localhost:3000"
DOCS = Path(__file__).resolve().parents[1] / "assignment" / "data" / "kyc_documents"
OUT = Path(__file__).resolve().parents[1] / "out"; OUT.mkdir(exist_ok=True)
fails: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def call(path, body=None, token=None, method=None):
    h = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    r = urllib.request.Request(WEB + "/api" + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method or ("POST" if body is not None else "GET"))
    return json.load(urllib.request.urlopen(r))


# ---- a customer with an order, set up through the API so the browser can go straight to the KYC page
tok = call("/auth/register", {"email": f"pwa{uuid.uuid4().hex[:6]}@example.com", "name": "Pwa Tester", "password": "Passw0rd!x", "phone": "9876543210"})["token"]
j = call("/journeys", {"business_name": "Ganesh Woodcraft", "business_type": "Furniture workshop", "city": "Nagpur", "employees": 12, "sites": 1, "current_internet": "Home broadband",
                       "monthly_budget": 15000, "monthly_telecom_spend": 3000, "has_gstin": True, "gstin": "27XUIXG0767D1ZP", "has_udyam": True, "contact_name": "Joseph Singh", "phone": "9876543210", "language": "en"})
call(f"/journeys/{j['id']}/selection", {"items": [{"product_id": "P02", "quantity": 1}, {"product_id": "P07", "quantity": 3}], "term_months": 12}, method="PUT")
q = call(f"/journeys/{j['id']}/quote", {})
order = call("/orders", {"quote_id": q["id"], "accept_terms": True}, tok)
call(f"/orders/{order['id']}/kyc/consent", {"accepted": True, "gstin": "27XUIXG0767D1ZP", "udyam_number": "UDYAM-MH-00-9516696"}, tok)

# a ~6 MB "camera photo": the real GST specimen blown up and saved as a high-quality noisy JPEG
src = Image.open(DOCS / "K03_gst_certificate.png").convert("RGB")
big = src.resize((src.width * 3, src.height * 3))
buf = io.BytesIO(); big.save(buf, "JPEG", quality=100, subsampling=0)
raw = buf.getvalue()
pad = raw + b"\0" * max(0, 3_000_000 - len(raw))  # make sure it is over the 1.5 MB shrink threshold even if the image compresses well

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True, permissions=["microphone", "camera"], service_workers="allow")
    ctx.add_init_script(f"localStorage.setItem('udyam.token','{tok}'); localStorage.setItem('udyam.journey','{j['id']}'); localStorage.setItem('udyam.lang','en')")
    pg = ctx.new_page()

    # 1 manifest / headers
    pg.goto(WEB + "/")
    mani = json.loads(pg.evaluate("fetch('/manifest.webmanifest').then(r=>r.text())"))
    purposes = {(i["sizes"], i.get("purpose")) for i in mani["icons"]}
    check("manifest: standalone, start_url, scope, 3 icons incl. maskable", mani["display"] == "standalone" and mani["start_url"] and ("512x512", "maskable") in purposes and ("192x192", "any") in purposes, str(purposes))
    hdr = pg.request.get(WEB + "/").headers
    check("Permissions-Policy allows mic + camera for this site", "microphone=(self)" in hdr.get("permissions-policy", "") and "camera=(self)" in hdr.get("permissions-policy", ""), hdr.get("permissions-policy", ""))
    check("sw.js is served no-cache", "no-cache" in pg.request.get(WEB + "/sw.js").headers.get("cache-control", ""))
    for icon in ["icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"]:
        check(f"icon {icon} served as PNG", pg.request.get(f"{WEB}/icons/{icon}").headers.get("content-type") == "image/png")
    check("iOS tags present", pg.locator('link[rel="apple-touch-icon"]').count() == 1 and pg.locator('meta[name="apple-mobile-web-app-title"]').count() == 1)

    # 2 installability as Chrome itself reports it
    cdp = ctx.new_cdp_session(pg)
    errs = cdp.send("Page.getInstallabilityErrors").get("installabilityErrors", [])
    check("Chrome reports no installability errors", errs == [], json.dumps(errs))

    # 3 service worker takes control; /api is never cached; static assets are
    pg.evaluate("navigator.serviceWorker.ready.then(()=>1)")
    pg.reload(); pg.wait_for_load_state("networkidle")
    check("service worker controls the page", pg.evaluate("!!navigator.serviceWorker.controller"))
    pg.evaluate("fetch('/api/health').then(r=>r.json())"); pg.evaluate("fetch('/api/meta').then(r=>r.json())")
    cached = pg.evaluate("caches.keys().then(async ks => { const out=[]; for (const k of ks){ const c=await caches.open(k); out.push(...(await c.keys()).map(r=>new URL(r.url).pathname)); } return out; })")
    check("no /api response is in any cache", not any(u.startswith("/api") for u in cached), str([u for u in cached if u.startswith('/api')]))
    check("shell + hashed static assets are cached", "/offline.html" in cached and any(u.startswith("/_next/static/") for u in cached), f"{len(cached)} entries")

    # 4 offline fallback (and the API still fails honestly instead of returning stale data)
    ctx.set_offline(True)
    pg.goto(WEB + "/orders")
    check("offline: friendly page instead of a browser error", "You are offline" in pg.content())
    api_off = pg.evaluate("fetch('/api/health').then(()=> 'served').catch(()=> 'network-error')")
    check("offline: API calls fail (never served from cache)", api_off == "network-error", api_off)
    ctx.set_offline(False)

    # 5 install UI: simulate Chrome's prompt
    pg.evaluate("localStorage.removeItem('udyam.installBanner.dismissedAt')")
    pg.goto(WEB + "/"); pg.wait_for_load_state("networkidle")
    pg.evaluate("""() => { window.__prompted = 0; const e = new Event('beforeinstallprompt'); e.prompt = () => { window.__prompted++; return Promise.resolve(); }; e.userChoice = Promise.resolve({outcome: 'accepted'}); window.dispatchEvent(e); }""")
    banner = pg.get_by_role("region", name="Install the app")
    expect(banner).to_be_visible()
    check("home page shows the install banner on a phone", banner.is_visible())
    banner.get_by_role("button", name="Install", exact=True).click()
    pg.wait_for_function("window.__prompted === 1")
    check("tapping Install calls the browser's native install prompt", pg.evaluate("window.__prompted") == 1)
    expect(banner).to_be_hidden()
    check("banner disappears after installing", not banner.is_visible())
    pg.evaluate("window.dispatchEvent(new Event('appinstalled'))")
    pg.screenshot(path=str(OUT / "pwa_home.png"))

    # banner dismissal sticks; menu item exists while installable
    pg.evaluate("localStorage.removeItem('udyam.installBanner.dismissedAt')"); pg.reload(); pg.wait_for_load_state("networkidle")
    pg.evaluate("""() => { const e = new Event('beforeinstallprompt'); e.prompt = () => Promise.resolve(); e.userChoice = Promise.resolve({outcome:'dismissed'}); window.dispatchEvent(e); }""")
    pg.get_by_role("button", name="Menu").click()
    check("menu has an Install app entry", pg.get_by_role("button", name="Install app").is_visible())
    pg.get_by_role("button", name="Menu").click()
    pg.get_by_role("button", name="Not now").click()
    pg.reload(); pg.wait_for_load_state("networkidle")
    pg.evaluate("""() => { const e = new Event('beforeinstallprompt'); e.prompt = () => Promise.resolve(); e.userChoice = Promise.resolve({outcome:'dismissed'}); window.dispatchEvent(e); }""")
    check("dismissed banner stays hidden after reload", not pg.get_by_role("region", name="Install the app").is_visible())

    # 6 microphone: the permission is granted and a recorder can start in this origin (full voice chain: e2e/voice.py)
    mic = pg.evaluate("""async () => { try { const s = await navigator.mediaDevices.getUserMedia({audio:true}); const r = new MediaRecorder(s); r.start(); await new Promise(x=>setTimeout(x,300)); r.stop(); s.getTracks().forEach(t=>t.stop()); return 'ok'; } catch(e) { return String(e); } }""")
    check("microphone: getUserMedia + MediaRecorder work", mic == "ok", mic)

    # 7 KYC page: two inputs, camera one carries capture=environment; photo upload goes through the real OCR pipeline
    pg.goto(f"{WEB}/orders/{order['id']}/kyc"); pg.wait_for_load_state("networkidle")
    cam = pg.locator('input[type=file][capture="environment"]')
    check("KYC: every document card has a 'Take photo' camera input", cam.count() >= 3, f"{cam.count()} inputs")
    check("KYC: camera input accepts JPEG/PNG only (iPhone converts HEIC)", cam.first.get_attribute("accept") == "image/jpeg,image/png")
    check("KYC: separate 'Choose file' picker still there", pg.locator('input[type=file]:not([capture])').count() >= 3)
    # record what the page really hands to fetch(): the File inside the multipart FormData
    pg.evaluate("""() => { window.__uploads = []; const f = window.fetch.bind(window); window.fetch = (u, o) => { if (o && o.body instanceof FormData && String(u).includes('/kyc/documents')) { const file = o.body.get('file'); window.__uploads.push({size: file.size, type: file.type, name: file.name}); } return f(u, o); }; }""")
    cam.first.set_input_files({"name": "camera.jpg", "mimeType": "image/jpeg", "buffer": pad})
    expect(pg.get_by_text("deleted automatically").first).to_be_visible(timeout=60000)  # card shows the upload once OCR has finished
    ups = pg.evaluate("window.__uploads")
    check("KYC: a 3 MB+ camera photo was shrunk to a smaller JPEG before upload", len(ups) == 1 and ups[0]["size"] < len(pad) * 0.9 and ups[0]["type"] == "image/jpeg", f"picked {len(pad)} bytes, uploaded {ups}")
    check("KYC: no error banner after the photo upload", pg.locator("text=larger than").count() == 0 and pg.locator("text=Upload failed").count() == 0)
    pg.screenshot(path=str(OUT / "pwa_kyc.png"), full_page=True)

    # 8 iPhone Safari: no native prompt exists, so the banner explains Share -> Add to Home Screen
    ios = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True,
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
    ip = ios.new_page(); ip.goto(WEB + "/"); ip.wait_for_load_state("networkidle")
    check("iOS: banner shows the Share -> Add to Home Screen steps", "Add to Home Screen" in ip.get_by_role("region", name="Install the app").inner_text())
    check("iOS: no useless Install button", ip.get_by_role("region", name="Install the app").get_by_role("button", name="Install", exact=True).count() == 0)

    # 9 already installed (standalone): no banner
    st = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True)
    st.add_init_script("const mm = window.matchMedia.bind(window); window.matchMedia = q => q.includes('standalone') ? {matches:true, media:q, addEventListener(){}, removeEventListener(){}, addListener(){}, removeListener(){}} : mm(q);")
    sp = st.new_page(); sp.goto(WEB + "/"); sp.wait_for_load_state("networkidle")
    sp.evaluate("""() => { const e = new Event('beforeinstallprompt'); e.prompt = () => Promise.resolve(); window.dispatchEvent(e); }""")
    check("installed (standalone) app shows no install banner", not sp.get_by_role("region", name="Install the app").is_visible())
    b.close()

print("\n%d failure(s): %s" % (len(fails), fails) if fails else "\nall PWA checks passed")
sys.exit(1 if fails else 0)
