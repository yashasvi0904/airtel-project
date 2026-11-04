"""LLM provider interface. The LLM interprets the customer's words and phrases explanations.
It never chooses products, prices or eligibility - the deterministic engine does, and replies are validated."""
import json
import logging
import re
from typing import Protocol

from ...config import get_settings
from .slots import extract_rules

log = logging.getLogger("advisor")

NEEDS_SCHEMA = {
    "type": "object",
    "properties": {
        "wants": {"type": "array", "items": {"type": "string", "enum": [
            "whatsapp", "sms", "email", "backup", "security", "firewall", "cctv", "pos", "website", "phone_system",
            "toll_free", "iot", "fleet", "failover", "static_ip", "guest_wifi", "sd_wan"]}},
        "mobile_lines": {"type": "integer"},
        "cameras": {"type": "integer"},
        "pos_counters": {"type": "integer"},
        "vehicles": {"type": "integer"},
        "machines": {"type": "integer"},
        "fibre_available": {"type": "boolean"},
        "pain_downtime": {"type": "boolean"},
        "priority": {"type": "string", "enum": ["price", "reliability"]},
        "mobile_only": {"type": "boolean"},
        "no_more_needs": {"type": "boolean"},
        "monthly_budget": {"type": "integer"},
    },
    "additionalProperties": False,
}

LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
              "gu": "Gujarati", "bn": "Bengali", "pa": "Punjabi", "ml": "Malayalam"}


class Provider(Protocol):
    name: str

    def extract(self, text: str, history: list[dict], needs: dict, last_question: str | None) -> dict: ...
    def phrase(self, template: str, facts: dict, history: list[dict], language: str) -> str | None: ...
    def answer(self, text: str, facts: dict, history: list[dict], language: str) -> str | None: ...


class MockProvider:
    """Offline provider: keyword extraction + deterministic templates. Used when no API key is configured."""
    name = "mock"

    def extract(self, text, history, needs, last_question):
        return extract_rules(text, last_question)

    def phrase(self, template, facts, history, language):
        return None

    def answer(self, text, facts, history, language):
        return None


SYSTEM_PHRASE = """You are the Accel Business advisor, helping a small-business owner in India choose telecom and digital services.
Rules you must follow:
- The FACTS JSON is the only source of truth for products, quantities, prices, eligibility and contract terms.
- Never invent, add, remove or rename a product. Never change or compute a rupee amount; copy amounts exactly as given.
- If asked to explain, use the 'reasons' in FACTS. If something is not in FACTS, say you will check, do not guess.
- Be warm, brief and plain-spoken (no jargon, no product codes). Use short lines. At most one question per reply.
- Reply in {language}. Keep product names in English."""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self):
        import anthropic

        s = get_settings()
        self.model = s.anthropic_model
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_seconds, max_retries=1)

    def _text(self, resp) -> str:
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    def extract(self, text, history, needs, last_question):
        rules = extract_rules(text, last_question)
        convo = history[-6:]
        prompt = (
            "Extract the business needs stated in the customer's latest message. Only include fields the customer actually "
            "stated or clearly implied; omit anything unknown. The assistant's last question topic was: "
            f"{last_question or 'none'}. A bare number answers that topic. 'nothing else' to an extras question means no_more_needs.\n"
            f"Conversation so far: {json.dumps(convo, ensure_ascii=False)}\nLatest message: {text}"
        )
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=1024, output_config={"effort": "low", "format": {"type": "json_schema", "schema": NEEDS_SCHEMA}},
                system="You convert a small-business owner's message (English, Hindi or Hinglish) into structured needs.",
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(self._text(resp) or "{}")
        except Exception as e:  # network, auth, schema - fall back to rules, never fail the chat
            log.warning("anthropic.extract failed: %s", type(e).__name__)
            return rules
        merged = {**data, **{k: v for k, v in rules.items() if k != "wants"}}
        merged["wants"] = sorted(set(data.get("wants", [])) | set(rules.get("wants", [])))
        return {k: v for k, v in merged.items() if v not in (None, [], "")}

    def _call(self, system: str, user: str, history: list[dict]) -> str | None:
        try:
            msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
            msgs.append({"role": "user", "content": user})
            while msgs and msgs[0]["role"] != "user":
                msgs.pop(0)
            resp = self.client.messages.create(model=self.model, max_tokens=1200, system=system, messages=_alternate(msgs),
                                               output_config={"effort": "low"})
            return self._text(resp) or None
        except Exception as e:
            log.warning("anthropic.call failed: %s", type(e).__name__)
            return None

    def phrase(self, template, facts, history, language):
        system = SYSTEM_PHRASE.format(language=LANG_NAMES.get(language, "English"))
        user = (f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\nWrite the assistant's next reply. Convey exactly the content of this "
                f"draft in natural, friendly wording (you may reorder or shorten, keep every rupee figure and product as given):\n{template}")
        return self._call(system, user, [])

    def answer(self, text, facts, history, language):
        system = SYSTEM_PHRASE.format(language=LANG_NAMES.get(language, "English")) + \
            "\nThe customer asked a free-form question. Answer it using only FACTS (catalogue + current recommendation). If it is outside scope, say so briefly and steer back to their bundle."
        return self._call(system, f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\nCustomer: {text}", history)


def _alternate(msgs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n" + m["content"]}
        else:
            out.append(m)
    return out


_provider_cache: dict[str, Provider] = {}


def get_provider() -> Provider:
    s = get_settings()
    choice = s.llm_provider.lower()
    key = f"{choice}:{bool(s.anthropic_api_key)}"
    if key in _provider_cache:
        return _provider_cache[key]
    prov: Provider
    if choice in ("anthropic", "auto") and s.anthropic_api_key:
        try:
            prov = AnthropicProvider()
        except Exception as e:
            log.warning("anthropic provider unavailable (%s); using mock", type(e).__name__)
            prov = MockProvider()
    else:
        prov = MockProvider()
    _provider_cache[key] = prov
    return prov


def numbers_in(text: str) -> set[int]:
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text or "") if n.replace(",", "").isdigit()}


def reply_is_grounded(reply: str, facts: dict, template: str) -> bool:
    """Reject LLM text that contains a rupee amount or product id that the engine did not produce."""
    allowed = numbers_in(json.dumps(facts)) | numbers_in(template)
    for m in re.finditer(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", reply):
        raw = m.group(1).replace(",", "")
        val = int(float(raw))
        if val not in allowed and round(float(raw)) not in allowed:
            return False
    for pid in re.findall(r"\bP\d{2}\b", reply):
        if pid not in json.dumps(facts):
            return False
    return True
