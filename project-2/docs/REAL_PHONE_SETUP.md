# Real Phone Mode Setup

Call Sense supports inbound telephone conversations through Twilio bidirectional Media Streams. The caller uses a normal phone; React is the operations dashboard. Telephone utterances enter the existing banking pipeline, including context, retrieval, verification, privacy and handoff. Banking records remain fictional.

Source support and simulated-provider tests do not prove carrier audio quality. A live test requires your own Twilio number, public HTTPS endpoint and Azure Speech resource. No credentials, number purchases, tunnels, recordings or real calls are created automatically.

## 1. Obtain provider access

Create a Twilio account and acquire a number with Voice capability. Copy its Account SID, Auth Token and E.164 phone number into your local configuration. Complete any trial caller verification required for your account. Number availability, geographic permissions and regulatory requirements depend on country and account; do not assume Twilio offers Indian +91 local numbers. Exotel/SIP adapters are not currently included.

See [Twilio inbound call configuration](https://www.twilio.com/docs/voice/tutorials/how-to-respond-to-incoming-phone-calls).

## 2. Obtain audio speech access

Create an Azure AI Speech resource and obtain its subscription key and region. The implementation sends each completed utterance as 16 kHz mono PCM WAV to Azure STT and converts Azure PCM TTS into telephone mu-law audio. It uses the existing HTTP client without an additional speech SDK. Set a supported voice and language. Browser and text demos do not require Azure.

References: [STT short-audio REST API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text-short), [TTS REST API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

## 3. Configure backend/.env locally

Copy `backend/.env.example` to `backend/.env` if you do not already have it. `.env` is ignored. Do not paste credentials into frontend code, chat transcripts, screenshots or Git. Fill:

```dotenv
APP_MODE=real_phone
TELEPHONY_PROVIDER=twilio
TELEPHONY_TRANSPORT=media
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
PUBLIC_BASE_URL=
PUBLIC_WS_URL=
OPERATIONS_TOKEN=
STT_PROVIDER=azure
TTS_PROVIDER=azure
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
AZURE_SPEECH_VOICE=en-IN-NeerjaNeural
VOICE_LANGUAGE=en-IN
ENABLE_STT=true
ENABLE_TTS=true
ENABLE_CALL_RECORDING=false
HUMAN_AGENT_NUMBER=
VOICE_END_SILENCE_MS=1200
VOICE_MAX_UTTERANCE_SECONDS=45
SILENCE_FIRST_SECONDS=30
SILENCE_SECOND_SECONDS=90
SILENCE_END_SECONDS=180
SILENCE_FINAL_ACTION=continue
MAX_CALL_DURATION_MINUTES=0
```

Generate a strong random operations token locally, for example with `backend/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep it private. `ADMIN_API_TOKEN` and `AGENT_PHONE_NUMBER` remain backward-compatible aliases; do not set conflicting aliases. Fill `HUMAN_AGENT_NUMBER` only with the approved support destination for real transfer. Arbitrary outbound dialing is not implemented.

Keep `MOCK_MODE=true` for the existing evidence-extractive generator. This setting controls AI generation, not telephone connectivity. For the optional Ollama LLM use `MOCK_MODE=false`, `LLM_PROVIDER=ollama`, and your installed `LLM_MODEL`. The same safety verification still applies. Neither mode has a real bank connection.

## 4. Start the backend and frontend

From the project root, in separate PowerShell terminals:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-frontend.ps1
```

Alternatively, from `backend`: `.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Run a single backend worker. Start scripts bind localhost, which works with a local tunnel. If existing background servers occupy the ports, run `powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1` first. Missing real-phone fields produce an explicit readiness state without disabling local modes.

## 5. Expose port 8000

Install and authenticate ngrok yourself, then run:

```powershell
ngrok http 8000
```

Copy your actual HTTPS forwarding origin into `PUBLIC_BASE_URL`, and the same origin using `wss://` into `PUBLIC_WS_URL`. Do not include endpoint paths, query strings or credentials. For example, `https://your-domain.ngrok.app` and `wss://your-domain.ngrok.app` are illustrative origins, not configured services.

Twilio cannot reach localhost/127.0.0.1 directly. The tunnel must support WebSocket upgrade. When its URL changes, update both environment values and the Twilio webhook, then restart FastAPI. Do not trust forwarded Host headers for signature validation.

## 6. Configure the Twilio number

In Twilio Console open **Phone Numbers > Manage > Active Numbers**, select your number, then **Voice configuration**. Newer navigation may use **Numbers & senders**. Choose Webhook as the incoming-call handler and HTTP POST as the method.

| Setting | Exact URL |
| --- | --- |
| A call comes in | `${PUBLIC_BASE_URL}/api/telephony/incoming` |
| Call status changes / status callback (POST) | `${PUBLIC_BASE_URL}/api/telephony/status` |
| Media WebSocket, supplied automatically by incoming TwiML | `${PUBLIC_WS_URL}/api/telephony/media` |

Replace the variables with actual configured origins. Save the number. Do not paste the WebSocket URL into the incoming HTTP webhook field. The incoming response contains `<Connect><Stream>` plus a one-use call binding. `/api/telephony/turn/{cid}` and `/dial-ended/{cid}` remain for Gather/Say compatibility.

Both HTTP callbacks and the WebSocket upgrade require the official Twilio request signature. Stream start checks Account SID, Call SID, internal call ID, one-use nonce and mu-law/8000/mono format. Never disable signature validation to solve a tunnel issue.

References: [Twilio media messages and clear/mark control](https://www.twilio.com/docs/voice/media-streams/websocket-messages), [Twilio request security](https://www.twilio.com/docs/usage/security).

## 7. Restart and inspect readiness

Restart FastAPI after editing `.env`. Open `http://127.0.0.1:8000/api/telephony/health`. It reports safe readiness, database status, missing field names and calculated URLs. It does not check billing, number ownership, remote speech credentials or provider connectivity; those require a manual live test.

Open `http://127.0.0.1:5173`, then **Settings > Telephony**. Enter your operations token in the sign-in form. The backend creates an eight-hour HttpOnly SameSite session; the token is not stored in sessionStorage or the JavaScript bundle. Keep the dashboard local during tunnel testing. For an HTTPS dashboard configure its exact origin in `CORS_ORIGINS` and use a same-origin reverse proxy for `/api` and WebSockets. Privileged direct API clients can supply `X-Admin-Token` over HTTPS.

## 8. Call and test

Dial your Twilio number from your permitted mobile phone. Listen for the greeting. In **Live Calls**, locate the masked caller and click **Monitor**. You do not start a phone call from the dashboard.

Try these synthetic scenarios:

1. "My debit card isn't working." Then "Online." Verify context, both transcript turns and spoken responses.
2. "I sent five thousand rupees using UPI yesterday, but the receiver hasn't received it." Then "It says successful." Verify amount, date, channel and clarification.
3. "I don't recognize a fifteen-thousand-rupee card transaction." Verify high risk and handoff. A configured support number enables transfer to that fixed destination; otherwise the assistant describes the simulated queue and keeps listening.
4. Use a synthetic secret-submission test. Verify redaction and the instruction not to share secrets. Never use actual credentials.
5. Interrupt playback, pause through the silence prompts, and continue asking questions on the same call. Finally hang up. Verify final state, duration, summary, latency and cleanup in Call History.

Audio STT produces completed utterances, not interim words. EndOfTurnDetector defaults to 1200 ms silence and a 60-second maximum utterance. It returns audio for one turn and resets; it never ends the CallSession. `VOICE_ACTIVITY_THRESHOLD` tunes the PCM RMS gate. Interruption requires 120 ms of above-threshold audio and sends Twilio `clear`; returned `mark` events finish playback and restore listening. This is an energy detector, not trained VAD/echo cancellation. Noisy lines can falsely trigger it. AI responses are not speculative or token-streamed.

## Call lifetime

Silence prompts default to 30, 90 and 180 seconds. `SILENCE_FINAL_ACTION=continue` keeps the call active; `reprompt` is also accepted. Legacy `end` and `transfer` values migrate to `continue`, including old `.env` files. `SILENCE_END_SECONDS` is now a final presence-prompt threshold, not a hangup deadline. `MAX_CALL_DURATION_MINUTES=0` means unlimited; a positive value intentionally enables a separate duration cap.

The browser safely restarts recognition after ordinary `onend`, responses and recoverable playback errors. Explicit End cancels recognition, speech and pending restarts. The phone stream stays open between turns. End, provider stop/disconnect, successful transfer, an enabled duration cap or exhausted fatal-failure recovery can terminate a call. Ordinary utterance completion, silence and playback completion cannot. See [CALL_LIFECYCLE_FIX.md](CALL_LIFECYCLE_FIX.md) for implementation and validation details.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Webhook not reached | Backend on 8000, tunnel, correct number and saved POST URL; Twilio debugger. |
| 403 invalid signature | Account Auth Token and exact HTTPS origin/path/query; update changed tunnel URLs. |
| WebSocket rejected | WSS origin, upgrades, complete configuration, matching identifiers and signature. |
| No caller audio | Base64 raw mu-law, 8000 Hz mono; inspect media errors. |
| Caller hears nothing | Azure key/region/voice, ENABLE_TTS, outbound media/mark and call status. |
| Distorted audio | Raw mu-law bytes, never WAV headers; resample TTS PCM from 16 kHz to 8 kHz. |
| Empty STT / clipped turns | Language, activity threshold, silence window; Azure expects 16 kHz mono WAV. |
| Immediate disconnect | Safe missing-field list, Twilio debugger, speech permissions, call/stream identifiers. |
| Works until tunnel restart | Update PUBLIC_BASE_URL, PUBLIC_WS_URL and webhook; restart backend. |
| Dashboard 401 | Sign in under Settings; session lasts eight hours; use the allowed origin. |
| Transfer fails | Approved E.164 destination, geographic/trial permissions and balance; call stays tracked. |
| Browser microphone does not restart | Grant permission and use Speak / Interrupt to retry. Permission/device failures suspend retries while keeping the call active. |

Temporary STT/AI failures reprompt and return to listening. TTS retries once; if retry and fallback both fail, native Twilio Say/Hangup handles fatal failure. Repeated consecutive voice failures exhaust the recovery budget and end as FAILED. Provider REST errors omit private exception details. A failed hangup needs retry or action in Twilio Console.

## Validation and boundaries

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -c backend/pytest.ini
```

From `frontend`:

```powershell
npm.cmd run build
npm.cmd run test:e2e
```

The repository uses React/JavaScript and Vite, not Next.js or TypeScript. There is no TypeScript or ESLint command. Browser tests use ports 8001/5174. Media tests use generated PCM and mocked speech/provider calls; they never place real calls. NumPy/SciPy are explicit audio dependencies; Twilio and httpx are direct dependencies.

Live carrier/speech quality still needs a manual test. One process owns the live media registry. The waveform is a state indicator. Azure synthesis is per response then paced to Twilio, not token-by-token. There is no real core banking/authentication, Exotel adapter, multi-worker routing, recording, arbitrary outbound dialing, production user roles or retention policy. Recording remains disabled even if its reserved flag changes. Optional local Whisper support for browser PCM calls is described in NATURAL_VOICE_UPGRADE.md; this telephone adapter continues to use Azure. Language metadata reflects configured recognition language, not automatic detection. Account-specific telephone requests remain unverified and receive safe guidance.

Signed Gather/Say remains selectable with `APP_MODE=mock`, `TELEPHONY_PROVIDER=twilio`, `TELEPHONY_TRANSPORT=gather`. It uses provider recognition and does not need Azure or PUBLIC_WS_URL. Browser/text/mock modes remain available with either transport.
