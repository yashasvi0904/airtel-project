"""Voice: server-side transcription for browsers whose own speech recognition is missing, blocked or offline.

The audio goes to the AI provider and is discarded: these tests check the plumbing (what is sent, limits, errors) with a faked Gemini."""
import base64
import json

import httpx

from app.services.advisor import providers
from tests.test_api_flow import PROFILE

WAV = b"RIFF" + b"\x00" * 2000  # content does not matter to the fake


def _journey(client, language="en"):
    return client.post("/api/journeys", json={**PROFILE, "business_name": "Voice Co", "language": language}).json()["id"]


def _gemini(handler):
    g = providers.GeminiProvider.__new__(providers.GeminiProvider)
    g.model, g.models, g._good, g._key = "m1", ["m1", "m2"], 0, "secret-key"
    g.http = httpx.Client(transport=httpx.MockTransport(handler))
    return g


def _post(client, jid, data=WAV, ctype="audio/wav", name="clip.wav"):
    return client.post(f"/api/journeys/{jid}/advisor/transcribe", files={"file": (name, data, ctype)})


def test_transcription_sends_the_clip_and_the_language_and_returns_text(client, monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        part = body["contents"][0]["parts"][0]["inlineData"]
        seen.update(mime=part["mimeType"], audio=base64.b64decode(part["data"]), system=body["systemInstruction"]["parts"][0]["text"], key=req.headers.get("x-goog-api-key"), url=str(req.url))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "mujhe fibre chahiye"}]}}]})

    monkeypatch.setattr(providers, "get_provider", lambda: _gemini(handler))
    from app.routers import journeys

    monkeypatch.setattr(journeys, "get_provider", lambda: _gemini(handler))
    r = _post(client, _journey(client, "hi"))
    assert r.status_code == 200 and r.json() == {"text": "mujhe fibre chahiye"}
    assert seen["mime"] == "audio/wav" and seen["audio"] == WAV and "Hindi" in seen["system"]
    assert seen["key"] == "secret-key" and "secret-key" not in seen["url"]  # key in a header, never in the URL


def test_transcription_falls_through_to_another_model_when_one_is_out_of_quota(client, monkeypatch):
    calls = []

    def handler(req: httpx.Request):
        calls.append(str(req.url))
        return httpx.Response(429, json={}) if "/m1:" in str(req.url) else httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hello"}]}}]})

    from app.routers import journeys

    monkeypatch.setattr(journeys, "get_provider", lambda: _gemini(handler))
    assert _post(client, _journey(client)).json() == {"text": "hello"} and len(calls) == 2


def test_transcription_needs_a_provider_that_can_hear_and_says_so_plainly(client):
    r = _post(client, _journey(client))  # the test environment runs the offline rules provider
    assert r.status_code == 501 and "type your answer" in r.json()["detail"]


def test_transcription_limits_and_validation(client, monkeypatch):
    from app.routers import journeys

    monkeypatch.setattr(journeys, "get_provider", lambda: _gemini(lambda req: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "x"}]}}]})))
    jid = _journey(client)
    assert _post(client, jid, data=b"x" * (journeys.MAX_VOICE_BYTES + 5)).status_code == 413
    assert _post(client, jid, ctype="application/pdf").status_code == 422
    assert _post(client, jid, data=b"tiny").json() == {"text": ""}  # nothing recorded: no call, no error
    assert client.post("/api/journeys/nope/advisor/transcribe", files={"file": ("a.wav", WAV, "audio/wav")}).status_code == 404


def test_a_provider_failure_is_a_friendly_retry_message_not_a_crash(client, monkeypatch):
    from app.routers import journeys

    monkeypatch.setattr(journeys, "get_provider", lambda: _gemini(lambda req: httpx.Response(500, json={})))
    r = _post(client, _journey(client))
    assert r.status_code == 424 and "try again or type" in r.json()["detail"]


def test_other_peoples_journeys_cannot_be_used_to_transcribe(client, monkeypatch):
    from tests.test_api_flow import auth

    owner = auth(client, "voiceowner@example.com", "Voice Owner")
    jid = client.post("/api/journeys", json={**PROFILE, "business_name": "Mine"}, headers=owner).json()["id"]
    from app.routers import journeys

    monkeypatch.setattr(journeys, "get_provider", lambda: _gemini(lambda req: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "x"}]}}]})))
    assert _post(client, jid).status_code == 403  # a journey bound to an account is private to it
