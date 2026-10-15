# Validation record

Validated locally on 24 September 2026, using the mock provider and synthetic banking records.

- Backend: **57 tests passed** (`backend/.venv/Scripts/python.exe -m pytest backend/tests`).
- Frontend: **8 Playwright tests passed**, covering desktop/mobile operations, multi-turn calls, verified account access, masked secrets, agent handoff, knowledge approval/reindex, intent/evaluation tools and the browser speech adapter.
- Production frontend: `npm run build` passed.
- Running application: frontend HTTP 200 at http://127.0.0.1:5173; backend health OK at http://127.0.0.1:8000/api/health; proxied configuration reports version 2.0.0, 110 intents and 223 approved knowledge records.
- Corpus: 110 intents with 18 example utterances each, 223 authored knowledge records, 368 evaluation cases.

## Recorded evaluation

The full run is saved in [evaluation-results.json](evaluation-results.json), and is available in the dashboard's Evaluation Lab.

| Measure | Result |
| --- | --- |
| Intent / top-2 intent accuracy | 100% / 100% |
| Decision accuracy | 99.73% (367 / 368) |
| Risk accuracy | 100% |
| Retrieval hit rate | 99.44% |
| Response grounding check | 100% |
| Escalation precision / recall | 100% / 100% |
| Unsafe-response proxy | 0% |
| PII / injection detection on labeled cases | 100% / 100% |
| Average processing latency | 30.70 ms |

One decision remains marked REVIEW: the unusually worded phishing-education question `I was wondering about what is phishing for a banking customer.` asks for clarification instead of responding. Retrieval also misses the expected document in two cases; these remain visible in the full result. Nothing is excluded to improve the displayed score.

These are synthetic regression measurements, not an independent banking benchmark or a claim of production safety. Domain wording templates overlap the model's taxonomy. Grounding and unsafe-response metrics use rule-based checks. Processing latency excludes real telephone transport, STT and TTS, which have not been measured here.

## Integration boundaries

Signed Twilio webhook, dialogue, retry/idempotency and demo-authentication behavior were tested with fixtures. No actual carrier call, paid API, real bank connection or physical microphone was used. Browser speech recognition was exercised through a test double; actual recognition depends on browser support and microphone permission. The current app uses mock telephony and synthetic account data.

Real phone operation requires a Twilio number, account credentials, a public HTTPS callback URL and an operations API token. Actual transfer additionally requires an agent number. Bidirectional Media Streams, codec conversion, utterance detection, two-turn banking context, clear/mark interruption, speech failure recovery and cleanup are now tested with simulated PCM and mocked speech services. Azure Speech credentials and PUBLIC_WS_URL are additionally required for media transport. The original Gather/Say transport remains available. See [README](../README.md) for configuration and remaining prototype boundaries.

Backend tests emitted a non-failing Starlette/httpx deprecation warning.

## Real-phone media upgrade validation

- 11 new tests cover audio conversion, turn boundaries, missing configuration, credential non-disclosure, invalid signatures/call binding, two-turn media flow, session/CSRF protection, provider failure, barge-in, secret redaction, speech failure recovery, spoken amounts and fraud escalation.
- All 57 backend tests passed; all 8 existing Chrome/Playwright browser tests passed; Vite production build passed.
- Tests prohibit real Twilio client calls and use speech doubles. No carrier call, live Azure request, provider purchase or tunnel was performed.
- The project is JavaScript/Vite and has no configured TypeScript or ESLint check.
- Existing evaluation figures above are the previously recorded run, not new live-carrier measurements.
- See [Real Phone Mode Setup](REAL_PHONE_SETUP.md) for the required manual acceptance test and remaining limitations.
