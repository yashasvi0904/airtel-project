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
        "connectivity": {"type": "string", "enum": ["fibre", "5g", "leased_line"]},
        "rejects": {"type": "array", "items": {"type": "string", "enum": [
            "whatsapp", "sms", "email", "backup", "security", "firewall", "cctv", "pos", "website", "phone_system",
            "toll_free", "iot", "fleet", "failover", "static_ip", "guest_wifi", "sd_wan"]}},
        "pain_slow": {"type": "boolean"},
        "budget_flexible": {"type": "boolean"},
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
- This is a continuing conversation: never greet, never say hello, never introduce yourself again.
- You do not recommend or choose products or bundles: the pricing engine does that. Explain, answer and clarify only. Never say "I recommend".
- Only use what the customer actually said in this conversation. Never assume a need (e.g. Wi-Fi) they have not stated.
- Quote money only as ₹ amounts that appear in FACTS (never as "899.0 INR"); catalogue list prices are ranges, not their price.
- If the customer says goodbye or that they need nothing, close politely and ask no question.
- Be warm, brief and plain-spoken (no jargon, no product codes). Use short lines. At most one question per reply.
- Reply in {language}. Keep product names in English."""


class _LLMProvider:
    """Shared prompts for the hosted LLMs. A subclass only implements `_generate` (one model call -> text).
    The model interprets words and phrases explanations; products, prices and eligibility stay in the engine."""
    name = "llm"

    def _generate(self, system: str, messages: list[dict], json_mode: bool = False) -> str:
        raise NotImplementedError

    def extract(self, text, history, needs, last_question):
        rules = extract_rules(text, last_question)
        convo = history[-6:]
        prompt = (
            "Extract the business needs stated in the customer's latest message. Only include fields the customer actually "
            "stated or clearly implied; omit anything unknown. The assistant's last question topic was: "
            f"{last_question or 'none'}. A bare number answers that topic. 'nothing else' to an extras question means no_more_needs.\n"
            "Questions about a product (e.g. 'what is CCTV?', 'why do I need failover?') are NOT requests for it: leave 'wants' empty.\n"
            "Things the customer says they do NOT want or need go in 'rejects', never in 'wants'. 'connectivity' is the kind of internet link they name "
            "(fibre, 5g, leased_line). A bare yes/no answers the assistant's last question: if that question asked whether fibre is available, yes means fibre_available=true.\n"
            "Judge ONLY the latest message; earlier messages are context, never repeat their fields. A greeting or small talk (hi, thanks, bye) has no needs: reply {}.\n"
            f"Reply with one JSON object only, using any of these fields: {json.dumps(NEEDS_SCHEMA['properties'])}\n"
            f"Conversation so far: {json.dumps(convo, ensure_ascii=False)}\nLatest message: {text}"
        )
        try:
            raw = self._generate("You convert a small-business owner's message (English, Hindi or Hinglish) into structured needs.",
                                 [{"role": "user", "content": prompt}], json_mode=True)
            data = json.loads(_strip_fence(raw) or "{}")
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except Exception as e:  # network, auth, quota, bad JSON - fall back to rules, never fail the chat
            log.warning("%s.extract failed: %s", self.name, type(e).__name__)
            return rules
        data = {k: v for k, v in data.items() if k in NEEDS_SCHEMA["properties"]}
        merged = {**data, **{k: v for k, v in rules.items() if k not in ("wants", "rejects")}}
        wants = set(data.get("wants") or []) | set(rules.get("wants", []))
        rejects = set(data.get("rejects") or []) | set(rules.get("rejects", []))
        merged["wants"] = sorted(wants - rejects)  # an explicit "no X" from either reader wins
        merged["rejects"] = sorted(rejects)
        return {k: v for k, v in merged.items() if v not in (None, [], "")}

    def _call(self, system: str, user: str, history: list[dict]) -> str | None:
        try:
            msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
            msgs.append({"role": "user", "content": user})
            while msgs and msgs[0]["role"] != "user":
                msgs.pop(0)
            return self._generate(system, _alternate(msgs)) or None
        except Exception as e:
            log.warning("%s.call failed: %s", self.name, type(e).__name__)
            return None

    def phrase(self, template, facts, history, language):
        system = SYSTEM_PHRASE.format(language=LANG_NAMES.get(language, "English"))
        user = (f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\nWrite the assistant's next reply. Convey exactly the content of this "
                f"draft in natural, friendly wording (you may reorder or shorten, keep every rupee figure and product as given):\n{template}")
        return self._call(system, user, [])

    def answer(self, text, facts, history, language):
        system = SYSTEM_PHRASE.format(language=LANG_NAMES.get(language, "English")) + \
            "\nThe customer asked a free-form question. Answer ONLY their latest message, using only FACTS (catalogue + current recommendation). Earlier goodbyes or refusals are over: the customer is back, so do not say goodbye. If it is outside scope, say so briefly and steer back to their bundle."
        return self._call(system, f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\nCustomer: {text}", history)


def _strip_fence(raw: str) -> str:
    raw = (raw or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.S)
    return m.group(1) if m else raw


class AnthropicProvider(_LLMProvider):
    name = "anthropic"

    def __init__(self):
        import anthropic

        s = get_settings()
        self.model = s.anthropic_model
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_seconds, max_retries=1)

    def _generate(self, system, messages, json_mode=False):
        cfg = {"effort": "low", "format": {"type": "json_schema", "schema": NEEDS_SCHEMA}} if json_mode else {"effort": "low"}
        resp = self.client.messages.create(model=self.model, max_tokens=1024 if json_mode else 1200, system=system,
                                           messages=messages, output_config=cfg)
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac", "audio/flac", "audio/3gpp"}


class GeminiProvider(_LLMProvider):
    """Google Gemini through the plain REST API (a free tier is available with a Google AI Studio key)."""
    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self):
        import httpx

        s = get_settings()
        self.model = s.gemini_model
        self.models = [self.model] + [m.strip() for m in s.gemini_fallback_models.split(",") if m.strip() and m.strip() != self.model]
        self._good = 0  # index of the model that last worked, so a quota-exhausted model is not retried on every call
        self._key = s.gemini_api_key
        self.http = httpx.Client(timeout=s.llm_timeout_seconds)

    def transcribe(self, audio: bytes, mime: str, language: str) -> str:
        """Speech to text for a short voice clip, in the customer's language (English words mixed in are fine). Nothing is kept."""
        import base64

        name = LANG_NAMES.get(language, "English")
        system = (f"You transcribe a short voice message from a small-business owner in India who is speaking {name}, possibly mixing in English or Hindi words. "
                  "Return ONLY the exact words spoken, in the script normally used for that language (Latin script for English). No quotes, no labels, no commentary. "
                  "If there is no intelligible speech, return an empty string.")
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}}, {"text": "Transcribe this audio."}]}],
                "generationConfig": {"maxOutputTokens": 512, "temperature": 0.0}}
        return self._post(body)

    def _post(self, body: dict) -> str:
        # the key travels in a header, never in the URL, so it cannot end up in logs
        last = None
        for i in list(range(self._good, len(self.models))) + list(range(0, self._good)):
            r = self.http.post(self.URL.format(model=self.models[i]), json=body, headers={"x-goog-api-key": self._key})
            if r.status_code in (404, 429, 503):  # quota / retired / overloaded: try the next model
                last = r
                continue
            r.raise_for_status()
            self._good = i
            break
        else:
            assert last is not None
            last.raise_for_status()
        cand = (r.json().get("candidates") or [{}])[0]
        return "".join(part.get("text", "") for part in (cand.get("content") or {}).get("parts", [])).strip()

    def _generate(self, system, messages, json_mode=False):
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages],
            "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.3},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return self._post(body)



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
    key = f"{choice}:{bool(s.anthropic_api_key)}:{bool(s.gemini_api_key)}"
    if key in _provider_cache:
        return _provider_cache[key]
    prov: Provider = MockProvider()
    order = {"anthropic": ["anthropic"], "gemini": ["gemini"], "auto": ["anthropic", "gemini"]}.get(choice, [])
    for which in order:
        if which == "anthropic" and s.anthropic_api_key:
            cls = AnthropicProvider
        elif which == "gemini" and s.gemini_api_key:
            cls = GeminiProvider
        else:
            continue
        try:
            prov = cls()
            break
        except Exception as e:
            log.warning("%s provider unavailable (%s); trying next", which, type(e).__name__)
    _provider_cache[key] = prov
    return prov


def numbers_in(text: str) -> set[int]:
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text or "") if n.replace(",", "").isdigit()}


def reply_is_grounded(reply: str, facts: dict, template: str) -> bool:
    """Reject LLM text that contains a rupee amount or product id that the engine did not produce."""
    allowed = numbers_in(json.dumps(facts)) | numbers_in(template)
    # amounts written either way round: "₹1,109", "Rs. 1109", "INR 1109" and "1109 INR" / "1109.0 rupees"
    for m in re.finditer(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:INR|Rs\b\.?|rupees?)", reply, re.I):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        if not raw:
            continue
        val = int(float(raw))
        if val not in allowed and round(float(raw)) not in allowed:
            return False
    for pid in re.findall(r"\bP\d{2}\b", reply):
        if pid not in json.dumps(facts):
            return False
    return True
