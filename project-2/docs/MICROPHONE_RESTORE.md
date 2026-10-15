# Restore the simple browser microphone path

1. **Root cause:** the natural-voice upgrade replaced immediate final delivery with continuous recognition, a 1200 ms timer and pending.sessions shared across recognition restarts. Abandoned interim results remained in that array. The timer rejected later valid final text whenever any old part was non-final, spoke a repeat prompt and cleared the buffer. Thus recognition could produce text without delivering it to the backend. Asynchronous phrase errors were a separate previously identified regression; the phrase recovery fix had not removed this buffer failure.
2. **Comparison:** no Git repository is present. The local before-natural-voice.zip backup shows the earlier Web Speech path: en-IN, interimResults=true, continuous=false and immediate final callback. before-mic-restore.zip preserves the implementation before this repair.
3. **Files:** modified frontend/src/hooks/useCallAudio.js, frontend/src/pages/Calls.jsx, backend/app/core/config.py, backend/app/services/speech.py and backend/.env.example. Added frontend/src/services/voiceDiagnostics.js and frontend/src/components/VoiceDiagnostics.jsx. Test files: microphone-restore.spec.js, microphone-diagnostics.spec.js, natural-voice.spec.js, call-lifetime.spec.js and backend/tests/test_browser_speech_config.py. Banking intent, RAG, knowledge, generation, trust and handoff code were not edited.
4. **Phrase bias:** disabled by default. Explicit opt-in still checks properties/constructor and falls back to a fresh instance without phrases after setter or asynchronous failure. Unsupported phrases do not disable the microphone or end the call.
5. **Provider:** Browser Voice Demo selects browser-web-speech first, independently of backend readiness. It bypasses the PCM energy gate. Backend capture is separately selectable and remains available when browser recognition/service is unavailable. Telephone routing is unchanged.
6. **Permission:** Web Speech permission/audio events track normal capture. The self-test independently requests getUserMedia({audio:true}), measures audio level and starts recognition. Denial, missing device and blocked speech service have distinct messages. Stop/unmount releases tracks; cancellation also releases a late permission result.
7. **Errors:** no-speech, aborted and network release the failed instance and retry without relying on onend. Repeated network failure can use a configured backend capture path. not-allowed/audio-capture pause retries; service-not-allowed uses available backend speech or explains the service limitation. Speak allows retry.
8. **Recognition end:** ends only one recognition session. Automatic restarts use bounded backoff, starting at 300 ms and capped at 4800 ms. Old unfinished text cannot block a later final.
9. **TTS:** recognition pauses during playback and resumes after completion/recoverable playback error. Generation guards ignore callbacks after End. Cleanup cancels only playback owned by that hook, so an idle self-test cannot cancel the main call's greeting.
10. **Environment:** defaults restored to STT_PROVIDER=browser and STT_MODEL=web-speech. BROWSER_STT_MODE=browser and BROWSER_PHRASE_BIAS=false are documented in .env.example. backend/.env was absent; no private environment file or credentials were created. VOICE_LANGUAGE=en-IN and PCM timing/threshold defaults remain. Browser recognition does not depend on PCM thresholds or Whisper weights.
11. **Tests:** Hello/card/long sentences, multiple turns, duplicate final suppression, abandoned interim recovery, errors without onend, explicit PCM mode, optional phrases, TTS restart, End, permission denial, audio levels, diagnostic masking and cleanup.
12. **Boundary:** browser tests inject recognition events and synthetic levels. They establish application delivery/lifecycle, not physical microphone quality or remote recognizer accuracy. Live Chrome acceptance remains manual.
13. **Manual steps:** refresh http://127.0.0.1:5173. In Live Calls, expand Operator voice diagnostics with no active call. Click Test microphone and allow access. Say Hello Call Sense; verify GRANTED, ACTIVE, changing audio level and finalTranscript. Stop the test. Select BROWSER_VOICE_DEMO and Start call. Say Hello, then My card is blocked. Verify transcripts and responses. Continue with It's a debit card and It stopped working at the ATM. Speak the long sentence from the request, then ask What is UPI? and What is NEFT? after playback. Verify one submission per final. End and verify recognition stays stopped. If levels move without a transcript, inspect lastRecognitionError and recognitionActive to distinguish capture from speech-service failure. Use no actual banking secrets.

Logs contain lifecycle event names, never transcript text or credentials. Operator transcript diagnostics are masked, ephemeral and not separately persisted. The self-test never sends audio/transcripts to the banking API.

## Verified results

- Backend: 134 tests passed (one existing non-failing Starlette/httpx deprecation warning).
- Browser: all 30 cases passed across the full run (29 passed) and corrected-fixture rerun (1 passed). The initial run lost its test server; it was not counted as successful. The last fixture correction renamed a counter that had collided with read-only window.closed.
- Vite production build passed. Frontend and backend health returned HTTP 200 after restart. Running configuration reports browser-web-speech, browser mode, en-IN, phrase bias disabled and no dependency on backend audio readiness.
- Comparison against the pre-repair backup confirms speech.py is the only modified backend service. The two backend configuration tests and ten new browser cases cover the requested restoration and diagnostics.

Run from the project root:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -c backend/pytest.ini
cd frontend
npm.cmd run build
npm.cmd run test:e2e
```

Physical microphone and browser-service acceptance is still unverified until the manual steps above are performed on the user's Chrome.

## Follow-up: final transcripts rejected by zero browser confidence

The latest inspected local call contained five completed voice transcripts. Every turn reported browser confidence 0.0 and was routed to speech_confirmation. This proves those utterances reached the backend; the remaining observed repeat loop was the confidence gate, not missing microphone audio. Earlier automated fixtures used .95 or omitted confidence, so they did not exercise this case.

The browser adapter now treats an exact-zero confidence on final text as unavailable for gating, retaining the reported zero in operator diagnostics. This is an explicit compatibility policy for this observed browser behavior, not a claim that zero universally means unavailable. No positive score is fabricated. Nonzero low confidence still requests clarification. Azure/Whisper confidence handling, transcript normalization, suspicious-text checks and banking safeguards are unchanged.

Modified: frontend/src/hooks/useCallAudio.js and frontend/tests/microphone-restore.spec.js. No environment variables changed in this follow-up. New tests compare the same final card transcript at confidence zero and .3: zero proceeds to the card-channel question with null confidence; .3 retains speech confirmation.

Refresh Chrome and start a new browser voice call. Say My credit card is blocked. Expected: the transcript is accepted and the assistant asks where the card failed, rather than repeatedly saying it did not hear you. In Operator voice diagnostics, reportedConfidence may show zero while confidenceStatus is UNAVAILABLE. End still stops recognition. Physical recognizer accuracy is not established by simulated browser events.

Follow-up validation: all 9 focused microphone browser tests passed, including both new confidence cases; Vite production build passed. Frontend/backend returned HTTP 200. This frontend-only change required no backend restart.
