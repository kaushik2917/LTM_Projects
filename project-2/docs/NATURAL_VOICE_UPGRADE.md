# Natural voice upgrade - 7 October 2026

1. **Root causes addressed:** recognition errors, prematurely finalized browser fragments, short pauses and internal demo wording in evidence. Acoustic accuracy still depends on the microphone and recognizer.
2. **STT change:** browser recognition now has a backend mono 16 kHz PCM path with optional faster-whisper, existing Azure support and explicit browser fallback. Startup never downloads weights.
3. **Providers:** local inference runs off the event loop with CPU int8 fallback and bounded concurrency. Azure REST preserves N-best hypotheses; Azure SDK phrase-list biasing is not implemented in this REST path.
4. **Vocabulary:** banking terms feed Whisper initial_prompt/hotwords and browser phrase hints when supported. Hints do not guarantee recognition.
5. **Capture:** 150 ms sustained start, 300 ms pre-roll, 1200 ms end silence, 300 ms post-roll and 60-second maximum capture. Browser microphone requests noise suppression, echo cancellation and automatic gain. A 700 ms pause is retained. Oversized speech prompts a repeat instead of submitting clipped audio. Energy detection is not trained VAD.
6. **Call lifecycle:** utterances remain within the same call. Browser restarts accumulate final segments, never submitting interim fragments. Capture pauses during processing/playback and resumes afterward. End releases tracks/audio context and cancels pending work. Existing interruption controls remain.
7. **Normalization:** mask raw text before storage; preserve financial values and identifiers; normalize conservative spelling/acronym cases. Ambiguous card/god alternatives request confirmation. Missing confidence remains missing; Whisper word probabilities are labeled uncalibrated.
8. **Context:** new card_blocked intent distinguishes an already blocked card from lost/stolen-card blocking requests. Debit/credit and channel follow-ups retain context. There are 111 intents, 225 seed knowledge records and the preserved 368-case evaluation corpus.
9. **Customer wording:** approved customer evidence removes internal demo language while operator records retain provenance. Generation and independent verification remain grounded in approved evidence. Privacy, identity checks and handoff remain. No unperformed financial action may be claimed.
10. **Inspector:** masked raw/normalized text, provider confidence when available and correction details appear in the existing operator inspector. Existing pages and layout are preserved.
11. **Configuration:** see backend/.env.example for Whisper model/device/compute, fallback/confidence, capture timings and microphone controls. VOICE_END_SILENCE_MS accepts the old threshold alias. CUSTOMER_SHOW_DEMO_LANGUAGE is a development option.
12. **Files:** new backend services stt.py, banking_vocabulary.py, transcript_normalizer.py and customer_response.py; frontend pcmCapture.js and audio-capture-worklet.js; optional requirements-speech.txt and scripts/setup-speech.py. Integration changes cover pipeline, intent, evidence, calls, speech/media, settings, voice hook and inspector. New backend/browser voice tests accompany these changes.
13. **Validation:** 91 backend tests and 14 Playwright tests passed; Vite production build passed. One non-failing Starlette/httpx deprecation warning remains. Tests cover normalization, value preservation, privacy, wording, capture timing/limits, metadata, WAV submission, lifecycle and cleanup. Browser speech fixtures are controlled; tests do not prove acoustic accuracy.
14. **External blocker:** faster-whisper 1.2.1 installed; CUDA is unavailable. Network policy returned a Site Blocked page instead of model weights. TLS verification remained enabled; no policy bypass was attempted. No valid weights are installed. Browser fallback remains available until approved weights are supplied.
15. **Manual acceptance:** backend/tests/voice-phrases.json contains requested phrases and a long utterance. Test real accents, microphones and noise, a 700 ms pause, long silence, follow-ups, playback interruption and End during processing. Actual card/god recognition accuracy and live telephone quality remain unverified.
16. **Limitations:** browser hints depend on capability; noise can trigger energy detection. Browser PCM retains explicit interruption controls. Telephone media remains Azure. No real core banking connection or production customer authentication has been added.

## Run

From the project root, separate PowerShell terminals:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1
powershell -ExecutionPolicy Bypass -File scripts/start-frontend.ps1
```

Command Prompt alternative, separate terminals:

```bat
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bat
cd frontend
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173. API docs: http://127.0.0.1:8000/docs. Optional model installation commands are in README.md.

References: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Azure REST STT](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text-short), [Azure phrase lists](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/improve-accuracy-phrase-list).

## Refreshed text evaluation

The preserved 368-case synthetic corpus completed through the running backend: intent accuracy 99.72%, decision accuracy 99.18%, retrieval hit rate 99.44%, and unsafe-response proxy 0%. These are in-domain text metrics, not independent acoustic or production-safety guarantees. Full rows, including mismatches, are in evaluation-results.json.
