# Call lifecycle fix - 29 September 2026

The existing application was changed in place. The dashboard layout, banking pipeline, 110 intents, knowledge corpus, demo verification, audit/security tools and provider architecture were retained.

## 1. Root cause

There were multiple independent lifecycle defects:

- `calls.silence_check` explicitly called provider hangup and `_finish(COMPLETED)` at the final silence threshold (70 seconds by default).
- `MediaSession.watchdog` independently hung up at that threshold regardless of the configured silence action.
- The media receive loop also treated 60 seconds without a WebSocket message as stream failure and cleaned up the call.
- Browser recognition `onend` only cleared the listening indicator. It did not restart recognition.
- Browser TTS errors and silence prompts did not resume listening, and ESCALATE responses explicitly disabled automatic listening.
- Audio callbacks were not scoped to a session/turn generation, so a canceled utterance could restart recognition later.

## 2. Files changed

Runtime:

- `backend/app/core/config.py`
- `backend/app/services/termination.py` (new)
- `backend/app/services/calls.py`
- `backend/app/services/media.py`
- `backend/app/services/audio.py`
- `backend/app/api/calls.py`
- `backend/app/api/telephony.py`
- `backend/app/schemas/operations.py`
- `frontend/src/hooks/useCallAudio.js`
- `frontend/src/pages/Calls.jsx`

Configuration/documentation:

- `backend/.env.example`
- `backend/.env`: only lifecycle settings updated; private provider values preserved and not printed.
- `README.md`
- `docs/REAL_PHONE_SETUP.md`
- `docs/CALL_LIFECYCLE_FIX.md`

Tests:

- `backend/tests/test_call_lifetime.py` (new)
- `backend/tests/test_system.py`
- `backend/tests/test_media.py`
- `frontend/tests/call-lifetime.spec.js` (new)

Existing browser tests also refreshed their screenshots under `docs/screenshots`.

## 3-4. Old and new behavior

| Event | Old behavior | New behavior |
| --- | --- | --- |
| Long customer silence | Hangup/completed, or configured transfer | Presence prompts, then continued listening; never a silence hangup |
| Empty browser recognition session | Microphone stayed stopped | Restart with bounded backoff while the call remains active |
| AI playback completion | Resume only in selected paths | Browser voice resumes listening, including clarification and escalation |
| Temporary TTS error | Browser microphone stayed inactive; phone could immediately fall back to hangup | Browser returns to listening; phone retries synthesis before fallback |
| Delayed callbacks | Could restart canceled resources | Session/generation checks and detached handlers ignore stale callbacks |
| Turn persistence | Updated summary during the call | Turns persist during the call; final summary and ended_at are created on termination |
| Call timer | Updated only with server polling | Advances each second from the original call creation time |
| Call History | Included active call rows | Shows terminal calls; active sessions remain in Live Calls |

One CallSession and one conversation ID are reused for every utterance. Authentication, context, entities, evidence, risk, handoffs and transcript history remain attached to that session. There is no fixed turn-count limit.

## 5. Environment values

| Variable | Previous default | New value |
| --- | --- | --- |
| VOICE_SILENCE_THRESHOLD_MS | 700 | 900 |
| VOICE_MAX_UTTERANCE_SECONDS | 30 | 45 |
| SILENCE_FIRST_SECONDS | 20 | 30 |
| SILENCE_SECOND_SECONDS | 40 | 90 |
| SILENCE_END_SECONDS | 70 | 180, now only a presence-prompt threshold |
| SILENCE_FINAL_ACTION | end | continue |
| MAX_CALL_DURATION_MINUTES | Not configured | 0, unlimited |

Existing `CALL_INITIAL_SILENCE_SECONDS`, `CALL_REPROMPT_SECONDS` and `CALL_END_SILENCE_SECONDS` aliases remain supported. Legacy silence actions `end` and `transfer` normalize to `continue` so old configuration cannot restore automatic idle hangups. `reprompt` is also accepted; both supported actions keep the call active. A positive maximum duration is intentionally enforced independently of silence, by the call-level watchdog.

## 6. End-of-turn detection

The existing EndOfTurnDetector is retained and explicitly documented as an utterance-only service. For media audio it emits a PCM utterance after 900 ms of silence, or at the 45-second utterance buffer limit, then clears its buffer for the next turn. It does not own a CallSession or call termination logic. The browser uses the speech recognizer's final result. Neither event closes the call or its persistent provider stream.

## 7. End-of-call detection

CallTerminationController permits explicit manual End, provider hangup/stop or disconnect, completed transfer, an intentionally enabled duration limit, and fatal failure after recovery is exhausted. Reasons are persisted with the final call record. Silence, utterance completion, recognition onend and TTS completion are not termination reasons. Terminal states cannot be resurrected by late state updates.

End immediately stops browser audio resources and invalidates pending callbacks. An in-flight backend turn can finish safe persistence under the per-call lock before the final summary/ended_at is saved. Transfer follows ESCALATING to TRANSFERRED; provider transfer failure keeps the session available. Normal goodbye wording does not automatically hang up.

## 8-9. Browser onend and TTS completion

The hook separately tracks active session, recognition, processing, playback, permission failure and pending restart. Ordinary recognition onend schedules a restart only when listening is appropriate. Repeated empty sessions back off from 300 ms to at most 4.8 seconds, avoiding a tight restart loop. Permission/device errors suspend retries while keeping the call active for typed input or an explicit Speak / Interrupt retry.

Normal recognition is suspended during processing and assistant playback to avoid transcribing the assistant. TTS completion/error sets WAITING and schedules listening again. Speak / Interrupt cancels playback and begins recognition on the same call. Escalation prepares a handoff but does not disable the browser conversational loop while waiting for transfer.

## 10. Race prevention and cleanup

- Audio generations invalidate old recognition/TTS callbacks; cancellation detaches handlers before abort/cancel.
- End disables the session before stopping resources and clears recognition restart timers.
- Session versions suppress a late turn response after End or a call switch.
- Reload versions prevent older monitoring requests overwriting newer snapshots.
- Browser state requests are serialized and carry the turn count; the backend rejects stale turn states under the per-call lock.
- Silence prompts carry the turn count and are ignored during pending processing or after End.
- No media receive inactivity deadline or silence callback can finish an active later turn.
- Shared dashboard monitoring stays available after End; call-owned audio callbacks are inactive. Navigation between dashboard pages preserves an active Live Calls session.

## 11. Automated coverage

Added tests exercise:

- 31 consecutive turns on each local mode, unchanged IDs/context, long idle periods, no premature summary/ended_at, and one idempotent final record.
- Rejection of stale playback state, obsolete silence checks and terminal-state resurrection.
- Recoverable AI failure, legacy configuration migration and independent opt-in duration limits.
- A media watchdog idle for a simulated hour without hangup or socket closure.
- Temporary STT/TTS failures followed by recovery on the same signed provider stream; provider stop ends it.
- The exact five-question conversation with real waits of 5, 10, 4 and 20 seconds.
- Browser FD/deposit conversation with 31 seconds plus another 5 seconds of silence.
- Forced recognition onend, TTS error recovery, permission denial/retry, barge-in, End during a delayed response, stale TTS callbacks after End, and escalation followed by transfer.
- Active calls excluded from finalized Call History.

Existing security, knowledge, evaluation, account verification, phone signatures, media codec, handoff, dashboard and mobile tests remain in the suites.

## 12. Results

- Backend: **67 passed**, using `backend/.venv/Scripts/python.exe -m pytest backend/tests -q -c backend/pytest.ini`.
- Browser: full suite **11 passed**, followed by **2 targeted passes** after adding the permission/transfer/history regression (12 distinct browser test cases validated overall).
- Production frontend: **build passed** after the final frontend change.
- The backend suite emits a non-failing Starlette/httpx deprecation warning. Vite logs socket-aborted messages when browser tests dispose their pages; the browser assertions passed.

Browser speech tests use a controllable recognition/TTS double. Media tests use generated audio and mocked provider/speech calls. No real carrier call or physical microphone quality is claimed as tested. Persistent unrecoverable voice failures can still terminate as FAILED after retry/fallback, as required; ordinary pauses and completed utterances cannot.
