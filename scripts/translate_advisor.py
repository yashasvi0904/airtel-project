"""Machine-translate the advisor's reply templates (questions, greeting, recommendation wrapper, Q&A replies) into the
supported languages -> backend/app/data/advisor_i18n.json, which templates.py / qa.py merge in at import.

English and Hindi are hand-written and never touched. Existing entries are never overwritten (hand-corrections survive).
  backend/.venv/Scripts/python scripts/translate_advisor.py [lang ...]
MACHINE translations: have a native speaker review before production (docs/LOCALIZATION.md).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from translate_locales import KEEP, NAMES, gemini_call  # noqa: E402

OUT = ROOT / "backend" / "app" / "data" / "advisor_i18n.json"
TEMPLATE_NAMES = ["QUESTIONS", "CLARIFY", "GREETING", "ACK", "REC_HEAD", "TIER_NAMES", "REC_TOTAL", "BUDGET_OK", "BUDGET_OVER", "EXCLUDED", "SAVINGS", "NEXT_STEP", "FALLBACK_HELP", "CHEAPER"]
PH = re.compile(r"\{\w+\}")

SYSTEM = f"""You are a professional translator localising the chat advisor of a small-business telecom and digital-services app in India
(internet, SIMs, WhatsApp, CCTV, billing) into {{lang}}. The advisor speaks to a shop owner in a warm, plain, respectful, spoken style.
Rules:
- Write ONLY in the native script of {{lang}}. Never use Latin transliteration or Hinglish-style romanisation (Latin letters only for the kept terms below).
- Natural everyday spoken words, not formal or literary. Short sentences.
- Keep placeholders like {{name}}, {{biz}}, {{city}}, {{amount}} EXACTLY as written. Keep the ** bold markers, the rupee sign and the bullet character.
- Keep in Latin script exactly: {KEEP}. Keep product names in English.
- Where the English asks the customer to type a word in quotes (for example 'nothing else', 'not sure', 'recommend'), keep that quoted English word
  unchanged inside the translated sentence, because the system recognises exactly that word.
- Keep numbers in Latin digits. Do not add explanations.
- Return JSON only: {{"translations": [ ... ]}} with exactly one translation per input, in the same order."""


def collect() -> dict[tuple, str]:
    from app.services.advisor import qa, templates as T

    flat: dict[tuple, str] = {}
    for n in TEMPLATE_NAMES:
        v = getattr(T, n)["en"]
        if isinstance(v, str):
            flat[(n,)] = v
        else:
            for k, t in v.items():
                flat[(n, k)] = t
    for k, d in qa.T.items():
        flat[("QA", k)] = d["en"]
    return flat


def ok(src: str, out: str) -> bool:
    return isinstance(out, str) and bool(out.strip()) and sorted(PH.findall(src)) == sorted(PH.findall(out)) and src.count("**") == out.count("**")


def main(langs: list[str]) -> int:
    key = None
    from app.config import get_settings

    key = get_settings().gemini_api_key
    if not key:
        sys.exit("GEMINI_API_KEY is not set in .env")
    model = os.environ.get("TRANSLATE_MODEL", "gemini-flash-lite-latest")
    flat = collect()
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    items = list(flat.items())
    bad = 0
    for code in langs:
        have = data.setdefault(code, {})
        todo = [(path, text) for path, text in items if not _get(have, path)]
        system = SYSTEM.replace("{lang}", NAMES[code])
        for i in range(0, len(todo), 25):
            chunk = todo[i:i + 25]
            try:
                got = gemini_call(key, model, system, [t for _, t in chunk])
                assert len(got) == len(chunk)
            except Exception as e:
                print(f"  [{code}] batch failed ({type(e).__name__}); retrying singly")
                got = []
                for _, t in chunk:
                    try:
                        got.append(gemini_call(key, model, system, [t])[0])
                    except Exception:
                        got.append("")
            for (path, src), out in zip(chunk, got):
                if ok(src, out):
                    _set(have, path, out.strip())
                else:
                    bad += 1
            OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(1.0)
        print(f"{code}: {len(items) - len(todo)} kept, {len(todo)} translated/attempted")
    print("failed validation:", bad)
    return 1 if bad else 0


def _get(d: dict, path: tuple):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def _set(d: dict, path: tuple, value: str) -> None:
    for p in path[:-1]:
        d = d.setdefault(p, {})
    d[path[-1]] = value


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if a in NAMES and a != "hi"] or [c for c in NAMES if c != "hi"])
