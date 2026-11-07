"""Server-side localisation of the engine's own sentences (recommendation reasons, units, product descriptions, eligibility text).

The browser and this module share the same translation files (frontend/src/lib/locales, synced to app/data/locales by
scripts/translate_locales.py), so a sentence is translated once and used everywhere. Translation never changes a fact:
only the wording of text the deterministic engine already produced. Anything without a translation stays English.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "locales"
SUPPORTED = ("en", "hi", "mr", "kn", "gu", "te", "ta", "bn", "pa", "ml")
# endonyms, in the order of how many leads in the supplied dataset prefer each language
LANGUAGE_NAMES = {"hi": "हिन्दी", "en": "English", "mr": "मराठी", "kn": "ಕನ್ನಡ", "gu": "ગુજરાતી", "te": "తెలుగు", "ta": "தமிழ்", "bn": "বাংলা", "pa": "ਪੰਜਾਬੀ", "ml": "മലയാളം"}


def normalize(lang: str | None) -> str:
    return lang if lang in SUPPORTED else "en"


@lru_cache(maxsize=16)
def _messages(lang: str) -> dict[str, str]:
    f = DATA / f"{lang}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[re.Pattern, str, list[str]]]:
    f = DATA / "_patterns.json"
    if not f.exists():
        return []
    return [(re.compile(p["re"]), p["tpl"], p["names"]) for p in json.loads(f.read_text(encoding="utf-8"))]


def _fill(text: str, vars: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(vars.get(m.group(1), m.group(0))), text)


def tr(text: str, lang: str | None, **vars) -> str:
    """Translate an English source string (with {placeholders}) into `lang`; falls back to English."""
    lang = normalize(lang)
    out = text if lang == "en" else _messages(lang).get(text, text)
    return _fill(out, vars) if vars else out


def _translate_one(message: str, lang: str, depth: int = 0) -> str | None:
    msgs = _messages(lang)
    if message in msgs:
        return msgs[message]
    for rx, tpl, names in _patterns():
        m = rx.match(message)
        if m and tpl in msgs:
            vals = [(_translate_one(v, lang, depth + 1) or v) if depth < 2 and re.search(r"[A-Za-z]{3,}", v) else v for v in m.groups()]
            return _fill(msgs[tpl], dict(zip(names, vals)))
    return None


_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def localize(message: str, lang: str | None) -> str:
    """Translate a sentence the engine already built (values embedded, or several sentences, or a ", "-joined list) into `lang`."""
    lang = normalize(lang)
    if lang == "en" or not message:
        return message
    one = _translate_one(message, lang)
    if one is not None:
        return one
    for splitter, joiner in ((_SENTENCES, " "), (re.compile(r",\s+"), ", ")):
        parts = splitter.split(message)
        if len(parts) < 2:
            continue
        out = [_translate_one(p, lang) for p in parts]
        if any(o is not None for o in out):
            return joiner.join(o if o is not None else p for o, p in zip(out, parts))
    return message


def tx(text: str) -> str:
    """Marks an English string for the extractor (translated later, where it is used, with tr())."""
    return text
