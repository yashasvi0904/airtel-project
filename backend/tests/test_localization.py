"""Ten-language support: the translation files are complete and well-formed, server sentences localise, and the advisor speaks each language.

These guard the failure modes that matter: a new English string added without being extracted/translated, a translation that lost
a {placeholder} (which would print a literal brace to a customer), and a language that silently falls back to English.
"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.services import i18n
from app.services.advisor import qa, templates as T
from tests.test_api_flow import PROFILE

ROOT = Path(__file__).resolve().parents[2]
LOC = ROOT / "frontend" / "src" / "lib" / "locales"
LANGS = [c for c in i18n.SUPPORTED if c != "en"]
PH = re.compile(r"\{\w+\}")


def _load_extractor():
    spec = importlib.util.spec_from_file_location("extract_strings", ROOT / "scripts" / "extract_strings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SOURCE = json.loads((LOC / "_source.json").read_text(encoding="utf-8"))


def test_every_string_the_frontend_translates_is_in_the_source_list():
    """Adding tr("...") without re-running scripts/extract_strings.py would ship an untranslatable string."""
    missing = sorted(_load_extractor().frontend_strings() - set(SOURCE))
    assert not missing, f"run scripts/extract_strings.py and scripts/translate_locales.py: {missing[:5]}"


def test_every_server_sentence_is_in_the_source_list():
    ex = _load_extractor()
    missing = sorted((ex.backend_strings() | ex.dataset_strings() | ex.python_tr_strings()) - set(SOURCE))
    assert not missing, f"re-run extraction: {missing[:5]}"


@pytest.mark.parametrize("lang", LANGS)
def test_translations_are_complete_and_keep_their_placeholders(lang):
    have = json.loads((LOC / f"{lang}.json").read_text(encoding="utf-8"))
    missing = [s for s in SOURCE if s not in have]
    assert len(missing) <= len(SOURCE) * 0.02, f"{lang}: {len(missing)} strings untranslated, e.g. {missing[:3]}"
    for src in SOURCE:
        out = have.get(src)
        if out is None:
            continue
        assert out.strip(), f"{lang}: empty translation for {src!r}"
        assert sorted(PH.findall(src)) == sorted(PH.findall(out)), f"{lang}: placeholders changed in {src!r} -> {out!r}"


@pytest.mark.parametrize("lang", LANGS)
def test_translations_are_really_in_the_target_script(lang):
    """Catches a language file that is just English copied over."""
    have = json.loads((LOC / f"{lang}.json").read_text(encoding="utf-8"))
    sample = [have[s] for s in SOURCE if s in have and len(s) > 25][:60]
    non_latin = sum(1 for t in sample if re.search(r"[^\x00-ɏ -⯿\U0001f000-\U0001faff]", t))
    assert non_latin >= len(sample) * 0.9, f"{lang}: only {non_latin}/{len(sample)} long strings contain native script"


def test_server_sentence_patterns_match_their_own_templates():
    pats = json.loads((LOC / "_patterns.json").read_text(encoding="utf-8"))
    assert len(pats) > 30
    for p in pats:
        filled = PH.sub("VALUE", re.sub(r"\{p\d+\}", "VALUE", p["tpl"]))
        assert re.match(p["re"], filled), f"pattern does not match its own template: {p['tpl']}"


def test_backend_and_frontend_share_identical_locale_files():
    for lang in LANGS:
        assert (LOC / f"{lang}.json").read_bytes() == (i18n.DATA / f"{lang}.json").read_bytes(), f"run scripts/translate_locales.py --sync ({lang})"
    assert (LOC / "_patterns.json").read_bytes() == (i18n.DATA / "_patterns.json").read_bytes()


@pytest.mark.parametrize("lang", ["hi", "ta", "mr", "ml"])
def test_engine_sentences_with_values_are_localised(lang):
    out = i18n.localize("Needs at least 5 employees (you have 3).", lang)
    assert out != "Needs at least 5 employees (you have 3)." and "5" in out and "3" in out and "{" not in out
    assert i18n.localize("a sentence nobody translated", lang) == "a sentence nobody translated"  # unknown stays as written
    assert i18n.localize("per camera", lang) != "per camera"


def test_unknown_language_falls_back_to_english_everywhere():
    assert i18n.normalize("xx") == "en" and i18n.normalize(None) == "en"
    assert i18n.tr("Got it: {items}.", "xx", items="3 cameras") == "Got it: 3 cameras."
    assert T.QUESTIONS["xx"]["pain"] == T.QUESTIONS["en"]["pain"] and T.chips_for("xx", "pain") == T.CHIPS["en"]["pain"]
    assert qa._say("greet", "xx") == qa.T["greet"]["en"]


@pytest.mark.parametrize("lang", LANGS)
def test_advisor_greets_and_asks_in_every_language(client, lang):
    j = client.post("/api/journeys", json={**PROFILE, "business_name": "Bhasha Traders", "language": lang}).json()
    assert j["language"] == lang
    first = client.post(f"/api/journeys/{j['id']}/advisor/start").json()
    text = first["messages"][0]["content"]
    assert "{" not in text and "Bhasha Traders" in text and first["question"] == "pain"
    english = T.GREETING["en"].format(name=", Joseph", biz="Bhasha Traders", city="Nagpur", emp=12, sites=1)
    assert text.split("\n\n")[0] != english.split("\n\n")[0], f"{lang}: greeting is still English"
    from app.services.advisor.engine import CURRENT_PHRASE

    assert text.split("\n\n")[-1] == T.QUESTIONS[lang]["pain"].format(current=i18n.tr(CURRENT_PHRASE["Home broadband"], lang))
    reply = client.post(f"/api/journeys/{j['id']}/advisor/message", json={"text": "4 cameras"}).json()
    assert "{" not in reply["reply"] and reply["chips"] == T.chips_for(lang, reply["question"])  # chips stay in words the engine understands


def test_the_ten_languages_are_advertised(client):
    langs = {x["code"]: x["label"] for x in client.get("/api/meta").json()["languages"]}
    assert set(langs) == set(i18n.SUPPORTED) and langs["ta"] == "தமிழ்" and langs["hi"] == "हिन्दी"


def test_switching_language_mid_journey_changes_the_advisor_language(client):
    j = client.post("/api/journeys", json={**PROFILE, "business_name": "Switch Co", "language": "en"}).json()
    client.post(f"/api/journeys/{j['id']}/advisor/start")
    assert client.put(f"/api/journeys/{j['id']}/language", json={"language": "mr"}).json() == {"language": "mr"}
    assert client.get(f"/api/journeys/{j['id']}").json()["language"] == "mr"
    reply = client.post(f"/api/journeys/{j['id']}/advisor/message", json={"text": "internet keeps going down"}).json()
    assert reply["question"] and T.QUESTIONS["mr"][reply["question"]].split("{")[0][:12] in reply["reply"]
    assert client.put(f"/api/journeys/{j['id']}/language", json={"language": "zz"}).json() == {"language": "en"}  # unknown -> English
    assert client.put(f"/api/journeys/{j['id']}/language", json={"language": "english"}).status_code == 422


def test_labels_inside_sentences_and_multi_sentence_reasons_are_translated():
    out = i18n.localize("You asked for a WhatsApp channel for customers.", "hi")
    assert "You asked" not in out and "channel" not in out and "WhatsApp" in out  # the embedded need label is translated too, the brand stays
    two = ("A dedicated 1:1 leased line gives the guaranteed bandwidth a production unit depends on. "
           "This replaces home broadband with a business-grade connection and business support.")
    hi = i18n.localize(two, "hi")
    assert "dedicated" not in hi and "This replaces" not in hi  # both sentences translated and re-joined
    assert i18n.localize("12-month commitment, 3+ product bundle", "ta") != "12-month commitment, 3+ product bundle"
    assert i18n.localize("per month", "xx") == "per month"


@pytest.mark.parametrize("lang", ["ta", "ml", "mr"])
def test_the_recommendation_itself_is_in_the_customers_language(client, lang):
    j = client.post("/api/journeys", json={**PROFILE, "business_name": "Reco Co", "language": lang}).json()
    client.post(f"/api/journeys/{j['id']}/advisor/start")
    text = client.post(f"/api/journeys/{j['id']}/advisor/message", json={"text": "I need 3 cameras and whatsapp, recommend"}).json()["reply"]
    assert "₹" in text and "{" not in text
    assert "You asked for" not in text and "/mo" not in text and "per camera" not in text  # reasons, units and price suffixes are localised
    assert T.REC_HEAD[lang].split("{")[0].strip()[:6] in text  # the language's own heading is used


def test_more_and_less_are_translated_for_the_savings_sentence():
    for lang in LANGS:
        assert i18n.tr("more", lang) != "more" and i18n.tr("less", lang) != "less", lang
