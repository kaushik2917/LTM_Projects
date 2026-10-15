# Browser phrase recovery and explicit human handoff

## Root causes

The frontend hook used presence checks and a synchronous try/catch around recognition.phrases. Chrome could accept that assignment then emit phrases-not-supported asynchronously from its recognition service. The generic onerror displayed the raw error with a typing suggestion, and each restart reapplied phrases. This produced a repeating capability failure rather than ordinary recognition.

The old complaint intent included human agent and speak to agent aliases. DecisionEngine escalated complaints and every HIGH-risk request using the same suspicious-interaction sentence. The telephone call service separately overwrote every escalation voice response with that sentence. A normal human-support request therefore acquired fraud wording even without a reported incident.

## Changes

1. Feature detection tracks recognitionSupported, phraseBiasSupported, interimResultsSupported and continuousSupported independently. The hook accepts SpeechRecognition or webkitSpeechRecognition.
2. Phrase setup requires the phrases property and a callable SpeechRecognitionPhrase constructor. Missing support skips configuration. A setter failure or asynchronous phrases-not-supported disables bias for the mounted browser session and creates a clean recognition instance without phrases. Recovery does not require an onend event.
3. Phrase failures log an internal warning; they do not block the microphone or show the raw error to customers. Permission/device failures remain distinct and pause automatic retries. Network errors report retrying; no-speech and aborted retain ordinary restart handling. PCM capture, microphone permission requests, Whisper prompts and the existing Azure path remain.
4. A deterministic human_agent_request intent covers direct, short, informal and Indian English requests. Direct requests precede clarification and authentication checks, while credential protection and injection safeguards keep precedence. Financial transfer instructions and negated handoff requests are not treated as agent requests.
5. Escalation reason is independent of risk. Normal handoff uses CUSTOMER_REQUESTED_HUMAN_AGENT with LOW risk; genuine current or previous security incidents retain HIGH risk and HIGH_RISK_FRAUD as an additional reason. Complaints and policy escalation have separate reasons and wording. Educational security questions do not become incidents.
6. The existing persisted Agent Queue receives a handoff packet with call/customer/profile, authentication, previous issue, masked history, entities, risk, trust, turn count and customer_requested_human. No authentication is needed merely to request support.
7. Browser/mock requests stay active in ESCALATING, with a professional support-queue acknowledgment. Automatic AI listening pauses for explicit human handoff. Existing fraud-call listening remains available. End and the explicit transfer action remain functional.
8. Telephone mode uses transfer wording only when a destination is configured. Existing media/Gather routing attempts provider transfer. Without a destination, the packet stays queued with natural customer wording. Simulated provider tests do not establish a live carrier connection.

## Files

Modified: frontend/src/hooks/useCallAudio.js, frontend/src/pages/Calls.jsx, backend/app/services/intent.py, pipeline.py, decision.py, calls.py and media.py. Added backend/app/services/handoff.py and backend/app/domain/human_support.json, with generated support knowledge records. Test changes: backend/tests/test_human_handoff.py, test_media.py, test_call_lifetime.py, frontend/tests/natural-voice.spec.js and call-lifetime.spec.js. Existing lifecycle tests now run call coroutines on the application event loop and wait for actual listening instead of a stale recognition reference.

## Manual acceptance

1. Refresh http://127.0.0.1:5173. Open Live Calls, select BROWSER_VOICE_DEMO and Start call. Allow Chrome microphone access; click Speak / interrupt if needed.
2. Say My card is blocked. Verify one transcript turn, a clarification, and an active call. Unsupported phrase bias should produce no customer error; recognition continues without it.
3. Say Transfer the call to a human agent. Verify human_agent_request, LOW risk, ESCALATE, customer-requested reason, support-queue wording and an active ESCALATING call. Inspect Agent Queue and the handoff history.
4. Start a new unverified call, ask What is NEFT?, then ask to speak to a person. Verify the prior banking issue is in the handoff and no verification challenge or fraud warning is added.
5. In a separate call say Someone made an unauthorized transaction. Transfer me to an agent. Verify HIGH risk and relevant security guidance.
6. End the call and verify no microphone restart. For live telephone acceptance, use the existing signed Twilio/Azure setup with an approved agent destination; no real calls are made by automated tests.

Physical microphone/recognition-service acceptance on the user's current Chrome remains a manual check. Automated browser tests use controlled recognition events; optional Whisper model weights remain blocked by the previously reported network policy.

Reference: [Speech recognition error definitions](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionErrorEvent/error) and [experimental phrases API](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/phrases).

## Results

- Backend: 132 passed, one non-failing Starlette/httpx deprecation warning. This includes 41 added regression cases.
- Browser: 20 cases passed across the final full run (19 passed) and a focused rerun of the corrected missing-constructor fixture (1 passed). Six new cases cover supported/absent phrase APIs, absent constructor, setter failure, asynchronous failure and spoken handoff. Existing permission, interruption, long-pause and lifecycle cases passed.
- Frontend: Vite production build passed. Local frontend and backend health both returned HTTP 200 after restart.
- Corpus: 112 intents and 227 seed knowledge articles. The preserved 368-case evaluation completed: intent accuracy 99.17%, decision accuracy 98.91%, retrieval hit rate 99.44%, unsafe-response proxy 0%. Two old complaint/MEDIUM labels now intentionally produce human_agent_request/LOW; labels were not rewritten to inflate scores. The remaining review rows include a blocked-card clarification and low-evidence remittance, re-KYC and phishing clarifications. Full results remain in evaluation-results.json. These are synthetic text metrics, not acoustic acceptance or production-safety guarantees.

Reproduce from the project root:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -c backend/pytest.ini
cd frontend
npm.cmd run build
npm.cmd run test:e2e
```
