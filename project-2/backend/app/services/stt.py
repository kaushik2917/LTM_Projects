"""Audio STT adapters. Audio and model work never run on the event loop."""
import asyncio
import importlib.util
import io
import threading
import wave
from pathlib import Path
from time import perf_counter
from typing import Protocol
import numpy as np
from app.core.config import settings
from app.services.banking_vocabulary import BANKING_PROMPT, BANKING_PHRASES

class STTUnavailable(RuntimeError):pass
class SpeechProvider(Protocol):
    async def transcribe(self,pcm16:bytes)->dict:...

def wav_bytes(pcm16):
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(pcm16)
    return output.getvalue()

def read_wav(data):
    try:
        with wave.open(io.BytesIO(data),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getcomptype())!=(1,2,16000,'NONE'):
                raise ValueError('Expected 16 kHz mono PCM WAV')
            if wav.getnframes()>16000*(settings.voice_max_utterance_seconds+3):
                raise ValueError('Audio exceeds configured utterance limit')
            pcm=wav.readframes(wav.getnframes())
            if len(pcm)!=wav.getnframes()*2 or len(pcm)<320:raise ValueError('Incomplete audio')
            return pcm
    except (wave.Error,EOFError) as exc:raise ValueError('Invalid WAV audio') from exc

def local_model_ready():
    if importlib.util.find_spec('faster_whisper') is None:return False
    model=Path(settings.whisper_model)
    if model.is_dir():return (model/'model.bin').is_file()
    root=Path(settings.whisper_download_root)/('models--Systran--faster-whisper-'+settings.whisper_model)
    return any((p/'model.bin').exists() for p in (root/'snapshots').glob('*'))

class BrowserSpeechProvider:
    async def transcribe(self,pcm16):
        raise STTUnavailable('Browser fallback requires browser capture')

class FasterWhisperProvider:
    def __init__(self):
        self.model=None;self.model_key=None;self.lock=threading.Lock()
    def recognize(self,pcm16):
        if not self.lock.acquire(blocking=False):raise STTUnavailable('Local recognizer busy')
        try:
            if not local_model_ready():raise STTUnavailable('Local speech model not installed')
            from faster_whisper import WhisperModel
            import ctranslate2
            key=(settings.whisper_model,settings.whisper_device,settings.whisper_compute_type)
            if self.model is None or self.model_key!=key:
                device=settings.whisper_device
                if device=='auto':device='cuda' if ctranslate2.get_cuda_device_count()>0 else 'cpu'
                options={'download_root':settings.whisper_download_root,'local_files_only':True,'cpu_threads':4}
                try:self.model=WhisperModel(settings.whisper_model,device=device,compute_type=settings.whisper_compute_type,**options)
                except Exception:
                    if settings.whisper_device!='auto' or device=='cpu':raise
                    self.model=WhisperModel(settings.whisper_model,device='cpu',compute_type='int8',**options)
                self.model_key=key
            samples=np.frombuffer(pcm16,dtype='<i2').astype(np.float32)/32768
            segments,info=self.model.transcribe(samples,language=settings.voice_language.split('-')[0],beam_size=5,
                initial_prompt=BANKING_PROMPT,hotwords=', '.join(BANKING_PHRASES),condition_on_previous_text=False,
                word_timestamps=True,vad_filter=False)
            segments=list(segments);words=[w.probability for s in segments for w in (s.words or [])]
            return {'text':' '.join(s.text.strip() for s in segments).strip(),'confidence':float(np.mean(words)) if words else None,
                'confidence_kind':'mean_word_probability_not_calibrated','alternatives':[],'provider':'faster_whisper',
                'model':settings.whisper_model,'detected_language':info.language,
                'no_speech_probability':max((s.no_speech_prob for s in segments),default=None)}
        finally:self.lock.release()
    async def transcribe(self,pcm16):return await asyncio.to_thread(self.recognize,pcm16)

class AzureSpeechProvider:
    async def transcribe(self,pcm16):
        from app.services.phone_speech import AzureSpeechProvider as AudioAdapter
        return await AudioAdapter().transcribe_pcm16(pcm16)

_local=FasterWhisperProvider()
class SpeechToTextService:
    def readiness(self):
        chosen=settings.stt_provider
        ready=local_model_ready() if chosen=='faster_whisper' else bool(settings.azure_speech_key and settings.azure_speech_region) if chosen=='azure' else False
        return {'provider':chosen,'audio_available':ready,'fallback':settings.stt_fallback_provider,
            'model':settings.whisper_model if chosen=='faster_whisper' else None,
            'biasing':'banking initial prompt + hotwords' if chosen=='faster_whisper' else 'REST N-best; phrase lists require Azure SDK' if chosen=='azure' else 'browser hints when supported'}
    async def transcribe(self,pcm16):
        started=perf_counter();fallback_used=False
        providers={'faster_whisper':_local,'azure':AzureSpeechProvider(),'browser':BrowserSpeechProvider()}
        chosen=providers.get(settings.stt_provider)
        if chosen is None:raise STTUnavailable('Unsupported speech provider')
        try:result=await chosen.transcribe(pcm16)
        except Exception:
            alternate=settings.stt_fallback_provider
            if alternate in providers and alternate not in {settings.stt_provider,'browser'}:
                try:result=await providers[alternate].transcribe(pcm16);fallback_used=True
                except Exception:raise STTUnavailable('Speech recognition unavailable; please repeat') from None
            else:raise STTUnavailable('Speech unavailable; use browser fallback or repeat') from None
        return {**result,'fallback_used':fallback_used,'transcription_latency_ms':round((perf_counter()-started)*1000,2)}
