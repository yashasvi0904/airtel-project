"""Voice in a real browser: a fake microphone plays a spoken sentence (e2e/../out/voice_test.wav, made with Windows speech) and we tap the mic.
Checks the whole chain: permission -> (browser speech service fails headless) -> recording fallback -> upload -> AI transcription -> text in the box.
Run with both servers up and a Gemini key configured:  python e2e/voice.py path/to/speech.wav"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WAV = str(Path(sys.argv[1]).resolve()) if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[1] / "out" / "voice_test.wav")
API, WEB = "http://localhost:8000/api", "http://localhost:3000"


def call(path, body=None):
    r = urllib.request.Request(API + path, data=json.dumps(body if body is not None else {}).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r))


j = call("/journeys", {"business_name": "Voice Co", "business_type": "Dental clinic", "city": "Pune", "employees": 8, "sites": 1, "current_internet": "Home broadband", "language": "en"})
call(f"/journeys/{j['id']}/advisor/start")

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-audio-capture={WAV}"])
    ctx = b.new_context(permissions=["microphone"], locale="en-IN")
    ctx.add_init_script(f"localStorage.setItem('udyam.journey','{j['id']}'); localStorage.setItem('udyam.lang','en')")
    pg = ctx.new_page()
    dialogs = []
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)[:150]))
    pg.goto(WEB + "/advisor")
    mic = pg.get_by_role("button", name="Speak your answer")
    expect(mic).to_be_visible(timeout=30000)
    print("mic visible; secure context:", pg.evaluate("window.isSecureContext"), "| browser SpeechRecognition:", pg.evaluate("!!(window.SpeechRecognition || window.webkitSpeechRecognition)"))
    mic.click()
    box = pg.get_by_label("Message")
    pg.wait_for_timeout(6000)                      # the person speaks, then taps the mic to finish
    if pg.get_by_role("button", name="Stop listening").count():
        pg.get_by_role("button", name="Stop listening").click()
    try:  # headless Chromium has no working speech service: nothing comes back, and the page offers the escape hatch
        pg.get_by_role("button", name="Record instead").wait_for(timeout=15000)
        print("browser recognition reported nothing -> tapping 'Record instead'")
        pg.get_by_role("button", name="Record instead").click()
    except Exception as ex:
        print("wait failed:", str(ex)[:300])
        print("no 'Record instead' offered (the browser's own recognition may have worked)")
    t0 = time.time()
    state = ""
    while time.time() - t0 < 40:
        stop = pg.get_by_role("button", name="Stop listening")
        if stop.count() and time.time() - t0 > 7:   # the fake microphone has played the whole sentence: stop recording
            stop.click()
        if box.input_value().strip():
            break
        problem = pg.locator("[role=status]").all_inner_texts()
        if problem and any("did not" in x or "not available" in x or "blocked" in x or "could not" in x.lower() for x in problem):
            state = " | ".join(problem); break
        pg.wait_for_timeout(500)
    text = box.input_value().strip()
    print("consent prompt shown:", bool(dialogs))
    print("page messages:", pg.locator("[role=status]").all_inner_texts()); print("text in the box:", repr(text), state, "| after", round(time.time() - t0, 1), "s")
    pg.screenshot(path=str(Path(WAV).parent / "voice_result.png"))
    b.close()
ok = any(w in text.lower() for w in ("fibre", "fiber")) and "camera" in text.lower()
print("page errors:", errors or "none")
print("RESULT:", "OK" if ok else "FAILED")
sys.exit(0 if ok and not errors else 1)
