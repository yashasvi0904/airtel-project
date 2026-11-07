"""Machine-translate the UI/server strings into the supported languages with Gemini, then verify them.

  backend/.venv/Scripts/python scripts/extract_strings.py          # 1. refresh the English source list
  backend/.venv/Scripts/python scripts/translate_locales.py        # 2. translate whatever is missing (resumable, safe to re-run)
  backend/.venv/Scripts/python scripts/translate_locales.py ta ml  # only some languages
  backend/.venv/Scripts/python scripts/translate_locales.py --check  # validate only (CI): placeholders, coverage
  backend/.venv/Scripts/python scripts/translate_locales.py --sync   # copy the locale files to the backend
  backend/.venv/Scripts/python scripts/translate_locales.py --retry-unchanged [lang]  # forget entries the model left in English, then re-run

Existing translations are never overwritten, so hand-corrections (e.g. by a native speaker) are kept. Only UI copy is sent to the model.
These are MACHINE translations: have a native speaker review them before production (see docs/LOCALIZATION.md).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
LOC = ROOT / "frontend" / "src" / "lib" / "locales"
NAMES = {"hi": "Hindi", "mr": "Marathi", "kn": "Kannada", "gu": "Gujarati", "te": "Telugu", "ta": "Tamil", "bn": "Bengali", "pa": "Punjabi (Gurmukhi script)", "ml": "Malayalam"}
BATCH = 40
PH = re.compile(r"\{\w+\}")
KEEP = "Accel Business, Udyam Digital, Biz Fibre, Airtel, WhatsApp, UPI, GSTIN, GST, Udyam, KYC, OTP, SIM, SIMs, CCTV, Wi-Fi, SD-WAN, POS, IVR, SMS, 5G, AirFiber, DPDP, PNG, JPG, MB, ID, PDF"

SYSTEM = f"""You are a professional translator localising a small-business telecom and digital-services app (internet, SIMs, WhatsApp, CCTV, billing)
for shop owners and small-business owners across India. Translate the English UI strings into {{lang}}.
Rules:
- Write ONLY in the native script of {{lang}}. Never use Latin transliteration or Hinglish-style romanisation (Latin letters only for the kept terms below).
- Use simple, natural, everyday spoken-register words a shop owner would use - not formal, literary or bureaucratic language.
- Keep every placeholder like {{name}}, {{n}}, {{amount}} EXACTLY as written (same braces, same spelling). Do not translate or reorder their names.
- Keep these terms in Latin script exactly as written: {KEEP}. Keep product names (e.g. "Biz Fibre 300", "Cloud CCTV") in English.
- Keep numbers in Latin digits (0-9), the rupee sign, and punctuation style (ending full stop, colon, ellipsis, arrows, brackets).
- Do not add explanations. Keep roughly the same length (UI buttons must stay short).
- Return JSON only: {{"translations": [ ... ]}} with exactly one translation per input, in the same order."""


def gemini_call(key: str, model: str, system: str, strings: list[str]) -> list[str]:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(strings, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 8192},
    }
    delay = 4.0
    for attempt in range(6):
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", json=body, headers={"x-goog-api-key": key}, timeout=120)
        if r.status_code in (429, 500, 503):
            time.sleep(delay); delay = min(delay * 2, 60)
            continue
        r.raise_for_status()
        parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        return json.loads(text)["translations"]
    raise RuntimeError("model unavailable after retries")


def valid(src: str, out: str) -> bool:
    return isinstance(out, str) and bool(out.strip()) and sorted(PH.findall(src)) == sorted(PH.findall(out)) and len(out) < max(40, len(src) * 4)


def translate(code: str, key: str, model: str) -> tuple[int, int]:
    path = LOC / f"{code}.json"
    have: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    source = json.loads((LOC / "_source.json").read_text(encoding="utf-8"))
    todo = [s for s in source if s not in have]
    system = SYSTEM.replace("{lang}", NAMES[code])
    done = failed = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        got: list[str] = []
        try:
            got = gemini_call(key, model, system, chunk)
            if len(got) != len(chunk):
                raise ValueError("length mismatch")
        except Exception as e:  # retry the batch one string at a time so one bad item cannot sink the rest
            print(f"  [{code}] batch {i // BATCH} failed ({type(e).__name__}); retrying singly")
            got = []
            for s in chunk:
                try:
                    got.append(gemini_call(key, model, system, [s])[0])
                except Exception:
                    got.append("")
        for s, t in zip(chunk, got):
            if valid(s, t):
                have[s] = t.strip()
                done += 1
            else:
                failed += 1
        path.write_text(json.dumps(have, ensure_ascii=False, indent=1), encoding="utf-8")  # resumable after every batch
        print(f"  [{code}] {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1.0)
    return done, failed


def sync_to_backend() -> None:
    """The backend localises engine sentences with the same files (backend/app/data/locales)."""
    import shutil

    dest = ROOT / "backend" / "app" / "data" / "locales"
    dest.mkdir(parents=True, exist_ok=True)
    for f in list(LOC.glob("[a-z][a-z].json")) + [LOC / "_patterns.json"]:
        shutil.copyfile(f, dest / f.name)
    print(f"synced {len(list(dest.glob('*.json')))} files to {dest.relative_to(ROOT)}")


def retry_unchanged(codes: list[str]) -> None:
    """Remove 'translations' that are just the English (the model sometimes echoes the input) so a re-run retries them.
    Entries with nothing to translate (times, brand/bank names, one-word terms) are left alone."""
    keep = re.compile(r"^[\W\d_]*$|^[\d: -]+$|Bank|^\{\w+\}")
    for code in codes or list(NAMES):
        path = LOC / f"{code}.json"
        d = json.loads(path.read_text(encoding="utf-8"))
        gone = [s for s, t in d.items() if s.strip() == t.strip() and len(s.split()) >= 2 and not keep.search(s)]
        for s in gone:
            del d[s]
        path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{code}: removed {len(gone)} untranslated entries; re-run to translate them")


def check() -> int:
    source = json.loads((LOC / "_source.json").read_text(encoding="utf-8"))
    bad = 0
    for code in NAMES:
        have = json.loads((LOC / f"{code}.json").read_text(encoding="utf-8"))
        missing = [s for s in source if s not in have]
        broken = [s for s in source if s in have and not valid(s, have[s])]
        print(f"{code}: {len(source) - len(missing)}/{len(source)} translated, {len(missing)} missing, {len(broken)} with broken placeholders")
        bad += len(broken) + (1 if len(missing) > len(source) * 0.02 else 0)
    return 1 if bad else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--check" in sys.argv:
        sync_to_backend()
        sys.exit(check())
    if "--retry-unchanged" in sys.argv:
        retry_unchanged(args)
        sys.exit(0)
    if "--sync" in sys.argv:
        sync_to_backend()
        sys.exit(0)
    from app.config import get_settings

    s = get_settings()
    if not s.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set in .env")
    model = os.environ.get("TRANSLATE_MODEL", "gemini-flash-lite-latest")  # the larger models hit free-tier quota quickly
    for code in args or list(NAMES):
        t0 = time.time()
        d, f = translate(code, s.gemini_api_key, model)
        print(f"{code} ({NAMES[code]}): +{d} translated, {f} failed validation, {time.time() - t0:.0f}s")
    sync_to_backend()
    sys.exit(check())
