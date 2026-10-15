"""One bounded, independently receiving audio session per live telephone call."""
import asyncio
import json
from contextlib import suppress
from time import monotonic, perf_counter
from uuid import uuid4
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.database.store import SessionLocal, Turn
from app.services import calls
from app.services.audio import AudioCodecService, EndOfTurnDetector
from app.services.phone_speech import audio_speech_provider

active_media: dict[str, 'MediaSession'] = {}


class MediaSession:
    def __init__(self, ws: WebSocket, cid: str, stream_id: str):
        self.ws, self.cid, self.stream_id = ws, cid, stream_id
        self.speech = audio_speech_provider()
        self.detector = EndOfTurnDetector(settings.voice_silence_threshold_ms, settings.voice_max_utterance_seconds, settings.voice_activity_threshold,pre_roll_ms=settings.voice_pre_roll_ms,post_roll_ms=settings.voice_post_roll_ms,start_ms=settings.voice_start_threshold_ms)
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        self.send_lock = asyncio.Lock()
        self.speech_lock = asyncio.Lock()
        self.generation = 0
        self.playback: str | None = None
        self.played = asyncio.Event()
        self.last_activity = monotonic()
        self.silence_stage = 0
        self.busy = False
        self.failures = 0
        self.barge_ms = 0.0
        self.caller_activity_version = 0

    async def send(self, message: dict):
        async with self.send_lock:
            await self.ws.send_json({'streamSid': self.stream_id, **message})

    async def interrupt(self):
        self.generation += 1
        self.playback = None
        self.played.set()
        await self.send({'event': 'clear'})

    async def say(self, text: str) -> float:
        async with self.speech_lock:
            return await self._say(text)

    async def _say(self, text: str) -> float:
        generation = self.generation
        started = perf_counter()
        # One transient synthesis failure must not terminate a conversation.
        try:
            pcm = await self.speech.generate_audio(text)
        except Exception:
            await calls.event(self.cid, 'voice_retry', {'stage': 'tts'})
            await asyncio.sleep(0.2)
            if generation != self.generation:
                return 0
            pcm = await self.speech.generate_audio(text)
        latency = round((perf_counter() - started) * 1000, 2)
        if generation != self.generation:
            return latency
        await calls.state(self.cid, 'SPEAKING')
        self.playback = uuid4().hex
        self.played.clear()
        for offset in range(0, len(pcm), 3200):
            if generation != self.generation:
                return latency
            await self.send({'event': 'media', 'media': {'payload': AudioCodecService.encode_provider_audio(pcm[offset:offset + 3200])}})
            await asyncio.sleep(len(pcm[offset:offset + 3200]) / 16000)
        if generation == self.generation:
            await self.send({'event': 'mark', 'mark': {'name': self.playback}})
            await asyncio.wait_for(self.played.wait(), timeout=10)
            self.playback = None
        self.last_activity = monotonic()
        await calls.state(self.cid, 'LISTENING')
        return latency

    async def fallback(self, text: str):
        try:
            await self.say(text)
        except Exception:
            # Twilio's native voice remains available when the audio TTS service fails.
            from app.services.telephony import native_failure
            await native_failure(self.cid)

    async def worker(self):
        self.busy = True
        await self.fallback(settings.call_greeting_text)
        self.busy = False
        while True:
            pcm = await self.queue.get()
            self.busy = True
            started = perf_counter()
            phase = 'stt'
            try:
                await calls.state(self.cid, 'TRANSCRIBING', True)
                transcript = await self.speech.transcribe(pcm)
                phase = 'ai'
                turn = await calls.call_turn(self.cid, transcript['text'], 'voice', transcript['transcription_latency_ms'], request_id=uuid4().hex,speech_metadata=transcript)
                phase = 'tts'
                reply = turn['voice_response']
                with SessionLocal() as db:
                    saved = db.get(Turn, turn['id'])
                    saved.data = {**saved.data, 'voice_response': reply,
                                  'speech_metadata': turn.get('speech_metadata',{})}
                    db.commit()
                tts_ms = await self.say(reply)
                metrics = {'stt_ms': transcript['transcription_latency_ms'], 'tts_ms': tts_ms,
                           'total_voice_turn_ms': round((perf_counter() - started) * 1000, 2)}
                with SessionLocal() as db:
                    saved = db.get(Turn, turn['id'])
                    saved.data = {**saved.data, 'speech_metadata': turn.get('speech_metadata',{}),
                                  'latency': {**saved.data['latency'], **metrics}}
                    db.commit()
                await calls.event(self.cid, 'voice_metrics', metrics)
                self.failures = 0
                if turn['decision'] == 'ESCALATE':
                    await calls.event(self.cid, 'handoff', {'simulated': not bool(settings.agent_phone_number)})
                    if settings.agent_phone_number:
                        await calls.transfer(self.cid)
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not (phase=='stt' and isinstance(exc,ValueError)):self.failures += 1
                await calls.event(self.cid, 'voice_error', {'stage': phase, 'retryable': self.failures < 2})
                if self.failures >= 2:
                    await self.fallback('I am sorry, the voice service is unavailable. Please contact your bank through its verified support channel. Goodbye.')
                    await calls.end(self.cid,failed=True,reason='fatal_failure')
                    return
                await self.fallback(settings.stt_failure_text if phase == 'stt' else settings.ai_failure_text)
            finally:
                self.busy = False
                self.queue.task_done()

    async def watchdog(self):
        while True:
            await asyncio.sleep(0.25)
            if calls.detail(self.cid)['state'] in calls.TERMINAL:
                await self.ws.close()
                return
            if self.busy or self.playback or not self.queue.empty():
                continue
            elapsed = monotonic() - self.last_activity
            stage = 3 if elapsed >= settings.silence_end_seconds else 2 if elapsed >= settings.silence_second_seconds else 1 if elapsed >= settings.silence_first_seconds else 0
            if stage > self.silence_stage:
                self.silence_stage = stage
                activity = self.last_activity
                activity_version = self.caller_activity_version
                await self.fallback('Are you still there?' if stage == 1 else "I'm still here whenever you're ready.")
                if activity_version == self.caller_activity_version:
                    self.last_activity = activity

    async def run(self):
        async def supervised(work):
            try:
                await work
            except asyncio.CancelledError:
                raise
            except Exception:
                await calls.event(self.cid, 'voice_error', {'stage': 'session', 'message': 'Voice session stopped safely'})
                with suppress(Exception):await self.ws.close()
        tasks = [asyncio.create_task(supervised(self.worker())), asyncio.create_task(supervised(self.watchdog()))]
        provider_stopped = False
        try:
            while True:
                # A quiet persistent transport is not an end-of-call event.
                raw = await self.ws.receive_text()
                if len(raw) > 24000:
                    raise ValueError('Media message too large')
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError('Expected media object')
                if message.get('streamSid') != self.stream_id:
                    raise ValueError('Stream identifier mismatch')
                event = message.get('event')
                if event == 'stop':
                    provider_stopped = True
                    break
                if event == 'mark' and message.get('mark', {}).get('name') == self.playback:
                    self.played.set()
                elif event == 'media':
                    media = message.get('media', {})
                    if media.get('track', 'inbound') != 'inbound':
                        continue
                    pcm = AudioCodecService.decode_provider_audio(media['payload'])
                    if self.detector.active(pcm):
                        self.caller_activity_version += 1
                        self.last_activity = monotonic()
                        self.silence_stage = 0
                        self.barge_ms += len(pcm) / 16
                        if self.playback and self.barge_ms >= 120:
                            await self.interrupt()
                            await calls.event(self.cid, 'interrupt', {'action': 'clear_provider_playback'})
                            await calls.state(self.cid, 'LISTENING', True)
                    else:
                        self.barge_ms = 0
                    utterance = self.detector.feed(pcm)
                    if self.detector.status=='UTTERANCE_TOO_LONG':
                        await calls.event(self.cid,'voice_error',{'stage':'capture','retryable':True})
                        if not self.busy:await self.fallback('Please repeat that in shorter parts so I can hear the full request.')
                    if utterance:
                        if self.queue.full():
                            await calls.event(self.cid, 'voice_backpressure', {'message': 'Utterance dropped while processing; repeat after the response.'})
                        else:
                            self.queue.put_nowait(utterance)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except (ValueError, KeyError, TypeError, AttributeError, TimeoutError):
            await calls.event(self.cid, 'voice_error', {'stage': 'media', 'message': 'Invalid or stalled stream'})
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            active_media.pop(self.cid, None)
            self.detector.buffer.clear()
            while not self.queue.empty():
                self.queue.get_nowait()
            # A dropped media stream must not leave an active provider call orphaned.
            if calls.detail(self.cid)['state'] not in calls.TERMINAL:
                with suppress(Exception):
                    await calls.end(self.cid, provider_ended=provider_stopped, reason='provider_hangup' if provider_stopped else 'provider_disconnect')
            with suppress(Exception):
                await self.ws.close()
