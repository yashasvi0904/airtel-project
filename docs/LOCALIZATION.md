# Localization and phone-first design

The case study asks for a journey "**on a phone, in their preferred language**". The dataset shows why that is not optional: its 5,000 leads prefer **ten languages**, and English plus Hindi cover only about two thirds of them.

| Language | Leads | Share | | Language | Leads | Share |
|---|---|---|---|---|---|---|
| Hindi हिन्दी | 2,137 | 42.7% | | Telugu తెలుగు | 207 | 4.1% |
| English | 1,168 | 23.4% | | Tamil தமிழ் | 207 | 4.1% |
| Marathi मराठी | 505 | 10.1% | | Bengali বাংলা | 111 | 2.2% |
| Kannada ಕನ್ನಡ | 253 | 5.1% | | Punjabi ਪੰਜਾਬੀ | 96 | 1.9% |
| Gujarati ગુજરાતી | 233 | 4.7% | | Malayalam മലയാളം | 83 | 1.7% |

## What the customer gets
- **Picks a language in one tap**: a language row on the first screen, a globe button in the header on every page (a bottom sheet with each language in its own script), and automatic detection from the phone's language list on first visit. The choice is remembered, and it follows the customer into their journey on the server, so the advisor answers in it too (`PUT /api/journeys/{id}/language`).
- **Every customer page** is translated: landing, onboarding, advisor, bundle, checkout, payment (UPI / net banking / card), orders, order tracking, KYC, sign-in. The back-office admin pages stay English (they are for staff).
- **The advisor** asks its questions, greets, acknowledges and presents the recommendation in the chosen language, without needing an LLM (templates, see below). Quick-reply chips are shown in the chosen language but send the original text.
- **Voice**: a microphone button speaks an answer into the chat in the chosen language, and a *Listen* button reads a reply aloud, using the phone's own speech engines (Web Speech API). Both appear only if the browser supports them for that language.
- **Fonts**: a font for each script (Devanagari, Kannada, Gujarati, Telugu, Tamil, Bengali, Gurmukhi, Malayalam), loaded only when a page uses those characters, with extra line height for stacked marks.
- **Dates** follow the language's locale; amounts keep the Indian digit grouping (₹1,23,456) in Latin digits.

## How it works (one set of translations, used by browser and server)
```
frontend tr("English text")  ─┐
backend sentences (AST)       ├─ scripts/extract_strings.py ─> locales/_source.json (+ _patterns.json)
dataset strings, statuses    ─┘                                        │
                                       scripts/translate_locales.py ───┘ (Gemini, placeholder-checked, resumable)
                                                      │
              frontend/src/lib/locales/<lang>.json ───┴─> synced to backend/app/data/locales/
scripts/translate_advisor.py ─> backend/app/data/advisor_i18n.json   (advisor templates and Q&A replies)
```
- Source strings are the **English text itself**: `tr("Pay {amount}", { amount })`. A missing translation falls back to English, never to a blank or a key.
- **Server sentences with values** ("Needs at least 5 employees (you have 3).") are matched by a pattern generated from the Python source, then re-filled into the translated template. The browser does this in `localizeMessage()`, the server in `services/i18n.localize()`, from the same files. So eligibility reasons, recommendation reasons, KYC findings and order events are translated without the backend having to produce message codes.
- Facts are never translated, only wording. Prices, products, eligibility and KYC verdicts come from the same deterministic code in every language.

## Adding or changing text
1. Write the English with `tr("...")` (or `tx("...")` for constants translated where rendered); a backend sentence is picked up automatically.
2. `backend/.venv/Scripts/python scripts/extract_strings.py` then `scripts/translate_locales.py` (translates only what is new; also syncs to the backend). Advisor templates: `scripts/translate_advisor.py`.
3. `scripts/find_untranslated.py` lists English that is not wrapped; the test-suite fails if a string is not in the source list, if any language is under 98% complete, if a translation loses a `{placeholder}`, or if a language file is not in its own script.

## Phone-first
Audited on an emulated Android phone (393×851, touch) across every customer page, before and after:
- no horizontal scroll on any page, in any language tested;
- tap targets: every button, link, stepper and option pill is at least 44×44 px (the third-party Google sign-in button is 40 px and cannot be resized);
- the **bundle page** keeps the monthly price and the *Get quote & checkout* button on screen (sticky bar) instead of at the bottom of a very long page; the advisor's *Review bundle* button is sticky once the recommendation is ready;
- the chat is sized to the visible viewport (`100dvh`) so the on-screen keyboard does not hide the input;
- inputs ask for the right keyboard (numeric for counts and amounts, telephone for mobile numbers, capitals for GSTIN, one-time-code for OTP) and carry `autocomplete` hints;
- a single *Back* control goes to the previous step of the journey (never browser history, so it cannot loop through a finished payment).

## Verified (and what the verification found)
- **43 localization tests** (`backend/tests/test_localization.py`): every string used in the frontend or produced by the server is in the source list; every language is >= 98% complete (all nine are 912/912) with identical `{placeholders}`; each language file is really in its own script; the sentence patterns match their own templates; browser and server share byte-identical files; the advisor greets, asks and presents the recommendation in each of the ten languages; unknown languages fall back to English everywhere.
- **`e2e/hindi.py`**: a whole purchase by a Hindi speaker on an emulated phone whose language list says Hindi: auto-detected on first visit -> onboarding -> typed Hindi in the advisor -> Hindi recommendation with prices -> bundle -> checkout -> UPI payment -> KYC -> switch to Tamil on the same page. Button labels are looked up in the real Hindi dictionary, so it fails if something the customer needs is untranslated.
- **`e2e/language_audit.py`**: every customer page x nine languages on an emulated Android phone: no page errors, no horizontal overflow or clipping, no leaked `{placeholder}`, only brand/product/city names left in Latin script. **`e2e/phone_audit.py`**: tap targets, tiny text, keyboards, clipping, in English.
- Looking at the screens (not just the numbers) found problems the automated checks had missed, all fixed:
  1. a **too-wide checkout page on every phone** (a table with a minimum width widened the whole layout to 538 px on a 412 px screen) - and the first overflow check could not see it, because an over-wide page makes mobile browsers widen the *layout viewport*, so comparing with `window.innerWidth` always says 0. The audits now compare with `screen.width`;
  2. the new **language chip row stretched the landing page** and the `overflow-hidden` hero clipped the heading - invisible to an overflow check, so the audits now also flag any element past the screen edge that is not inside a deliberately scrollable box;
  3. the **language sheet was clipped to the header** (an ancestor with `backdrop-filter` becomes the containing block of `position: fixed`) - it is now rendered through a portal;
  4. **Hindi came back romanised** ("alerts aur promotions ke liye...") for 26 strings because the prompt did not say Devanagari - caught by the script-check test, fixed by hand and by a stricter prompt;
  5. the model **echoed the English** for ~100 strings in some languages (Bengali the most) - found by a scan for translations identical to their source, retried;
  6. engine sentences that **start with a value**, joined **multi-sentence** reasons, and labels **embedded inside** a translated sentence were first left in English; the matcher now handles all three.

## Honest limits
- **The eight non-Hindi, non-English translations are machine translations** (Gemini), checked automatically for placeholders and script but **not reviewed by native speakers**. Hindi and English were written by hand for the original landing/onboarding/advisor copy and 26 Hindi strings were corrected by hand; everything else, in every language, is machine-translated. Get a native review before launch, especially for payment, KYC and consent wording (legal text such as the DPDP notice needs a proper translation).
- **Typed free text in the offline rules mode is understood in English, Hindi and Hinglish only.** In the other eight languages the advisor's questions and answers are fully translated, but understanding what the customer *types* needs an LLM provider (Gemini works on the free tier) or the quick-reply chips / numbers. Voice produces text in the chosen language, so it has the same limit.
- Product *names* (Biz Fibre 300, Cloud CCTV) stay in English by design; business categories and catalogue descriptions are translated.
- Some engine sentences built from several parts (for example a long list of alternatives) are only partly translated when no pattern covers them; they fall back to English rather than breaking.
- Speech recognition and read-aloud depend on the phone's browser and voices; recognition may use the browser vendor's cloud service. Not tested with real speech here (headless browser), only feature-detected.
- **Translation tooling used the Gemini free tier**, which has daily quotas: the larger model ran out, so most of the work used `gemini-flash-lite-latest` / `gemini-3.1-flash-lite` (`TRANSLATE_MODEL=...`). The scripts are resumable and only translate what is missing.
- **Admin pages stay English** (staff tool). The language row sends the language to the server (`PUT /api/journeys/{id}/language`) so the advisor follows; the dataset language field is not otherwise used for scoring.
- Fonts come from Google Fonts at build time (as the Devanagari one already did); self-host them for an offline build.
