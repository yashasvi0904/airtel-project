# The advisor: how the conversation works

The advisor is the front door of the journey. It must feel like talking to a sensible salesperson who listens, asks only what matters, and never pushes products the owner did not ask for - while every product and price still comes from the deterministic engine.

## What was wrong with v1 (and why it was rebuilt)
- A fixed question list: after "I need fibre" it still asked "how many mobile SIMs?", because the next question did not depend on the answers.
- "Yes"/"no" were read without knowing which question they answered ("no" to "any CCTV?" was treated as a global refusal).
- Negations ("no antivirus", "I don't need CCTV") were read as requests, and the wrong products were added.
- Quantities in words or with units ("eight cameras", "5k", "do lakh") were missed or mis-assigned.

## v2 design

```
customer text (typed or voice) ─► extract_rules()  ─┐
                                                    ├─► merge_needs() ─► next_question() ─► reply
Gemini / Claude structured JSON (optional)       ───┘      │                                 │
                                                           └────► recommender (deterministic) ◄┘ when the plan is complete
```

1. **Understanding** (`services/advisor/slots.py`). A deterministic reader (English, Hindi, Hinglish, plus romanised and native-script regional keywords) fills a "needs" object: wants, rejects, link type (fibre / leased line / hotspot), quantities (SIMs, cameras, counters, sites, staff), budget, current internet, pain point. It handles negation ("no antivirus"), number words, `k`/`lakh`, and yes/no *in the context of the question just asked*. When an LLM is configured, its structured extraction is merged with the rules' (union; anything the customer rejected wins).
2. **Planning** (`next_question`). Each segment has its own discovery order (micro: pain → connectivity → channels → physical → budget; professional: adds office tools; multi-site; manufacturer: machines before WhatsApp). A question is skipped when the answer is already known or irrelevant (a hotspot user is not asked "what is wrong"; someone who said "leased line" is not asked fibre vs. hotspot). Follow-ups for quantities come first ("how many cameras?"). At most five questions; none repeated.
3. **Behaviour you can see**: a "What I understood" bar echoes the needs back (the owner can correct it), a progress indicator, quick-reply chips per question, one clarifying question for a vague yes ("Which ones?"), and a second vague answer is treated as "nothing more" instead of looping. Assumptions (e.g. one SIM per staff member) are said out loud.
4. **Recommending** (`services/recommender.py`). Honours link type and rejections; if the owner asked for something they are not eligible for (a leased line below the size or GSTIN rules) it appears under "not available, and why" instead of being silently swapped.
5. **Explaining**. Templates in ten languages (Hindi and English hand-written, the rest generated and checked for placeholders) or the LLM, whichever is configured. `reply_is_grounded()` discards any LLM reply that contains a rupee amount or product id the engine did not produce.
6. **Free-form questions** ("what is the setup fee?", "is GST included?") are answered from the catalogue and the current quote by `advisor/qa.py`; anything outside that gets an honest "I can't answer that here".

## Voice
- Tap the mic. Method 1 is the browser's own speech recognition (Chrome/Edge/Android, live text while speaking).
- If it is missing, blocked, offline, or dies instantly (Brave, Chromium builds), the page records up to 25 s and POSTs it to `/journeys/{id}/advisor/transcribe`, which has Gemini turn it into text in the customer's language. A one-time consent prompt says where the clip goes; it is never stored.
- Every failure shows a sentence saying why (insecure origin, blocked mic, no mic, heard nothing, offline, language not supported, server error) and a **Record instead** button; nothing fails silently.
- Browsers refuse the microphone on plain `http://<LAN-ip>:3000`. Use `localhost`, or HTTPS (a tunnel) on a phone.
- Replies can be read aloud where the device has a voice for the language.

## Tests and evidence
- `backend/tests/test_advisor_dialogue.py` (28): the "fibre → mobile SIMs" regression, negation, quantities, context-aware yes/no, skip rules per segment, clarify-once, no repeated question, ineligible leased line.
- `backend/tests/test_voice.py` (6): endpoint validation, size/format limits, empty clip, missing provider, provider failure.
- `e2e/voice.py`: real Chromium with a fake microphone playing synthesized speech through the whole chain.
- Live Gemini conversations (English, Hindi, Hinglish) were run by hand; Claude's provider has never run (no API credit).

## Known limits
- Rules understand a fixed vocabulary; unusual phrasing falls back to a clarifying question or, with an LLM key, to the model's reading.
- Regional-language templates and keywords are machine-made and not reviewed by native speakers.
- Speech recognition has been exercised with synthesized speech, not yet with a human voice on a physical phone.
