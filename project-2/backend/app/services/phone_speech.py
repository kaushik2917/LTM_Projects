"""Audio speech adapters, independent of the telephone transport."""
import re
from time import perf_counter
from typing import Protocol
from xml.sax.saxutils import escape, quoteattr
import httpx
from app.core.config import settings
from app.services.audio import AudioCodecService


class AudioSpeechProvider(Protocol):
    async def transcribe(self, pcm: bytes) -> dict: ...
    async def generate_audio(self, text: str) -> bytes: ...


class AzureSpeechProvider:
    """Short utterance REST recognition and 16 kHz PCM synthesis."""
    def __init__(self):
        if not settings.azure_speech_key or not re.fullmatch(r'[a-z0-9-]+', settings.azure_speech_region):
            raise ValueError('Azure Speech configuration missing or invalid')

    async def transcribe(self, pcm: bytes) -> dict:
        return await self.transcribe_pcm16(AudioCodecService.resample_audio(pcm,8000,16000))

    async def transcribe_pcm16(self,pcm):
        from app.services.stt import wav_bytes
        started = perf_counter()
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f'https://{settings.azure_speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1',
                params={'language': settings.voice_language, 'format': 'detailed'},
                headers={'Ocp-Apim-Subscription-Key': settings.azure_speech_key, 'Content-Type': 'audio/wav; codecs=audio/pcm; samplerate=16000'},
                content=wav_bytes(pcm))
            response.raise_for_status()
            data = response.json()
        best = (data.get('NBest') or [{}])[0]
        text = best.get('Display') or data.get('DisplayText', '')
        if not text.strip():
            raise ValueError('No speech recognized')
        return {'text': text, 'detected_language': settings.voice_language, 'confidence': best.get('Confidence'),
                'transcription_latency_ms': round((perf_counter() - started) * 1000, 2), 'provider': 'azure', 'confidence_kind':'azure_nbest', 'alternatives':[{'text':x.get('Display',''),'confidence':x.get('Confidence')} for x in data.get('NBest',[])[:5]]}

    async def generate_audio(self, text: str) -> bytes:
        ssml = f'<speak version="1.0" xml:lang={quoteattr(settings.voice_language)}><voice name={quoteattr(settings.azure_speech_voice)}>{escape(text)}</voice></speak>'
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(f'https://{settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1',
                headers={'Ocp-Apim-Subscription-Key': settings.azure_speech_key, 'Content-Type': 'application/ssml+xml',
                         'X-Microsoft-OutputFormat': 'raw-16khz-16bit-mono-pcm', 'User-Agent': 'CallSense'}, content=ssml.encode())
            response.raise_for_status()
            if not response.content or len(response.content) > 4_000_000 or len(response.content) % 2:
                raise ValueError('Invalid speech audio')
            return AudioCodecService.resample_audio(response.content, 16000, 8000)


def audio_speech_provider() -> AudioSpeechProvider:
    if settings.stt_provider != 'azure' or settings.tts_provider != 'azure':
        raise ValueError('Media transport requires configured audio STT and TTS providers')
    return AzureSpeechProvider()
