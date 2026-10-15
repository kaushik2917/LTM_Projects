from typing import Protocol
from app.core.config import settings

class STTProvider(Protocol):
    async def transcribe(self,packet:dict)->dict:...
class BrowserSTTProvider:
    async def transcribe(self,packet:dict)->dict:
        text=packet.get('text','').strip()
        if not text or len(text)>2000:raise ValueError('Transcript must contain 1-2000 characters')
        return {'text':text,'latency_ms':packet.get('stt_ms'),'provider':'browser-web-speech' if packet.get('source')=='voice' else 'typed-test-input'}
class TwilioSTTProvider(BrowserSTTProvider):
    async def transcribe(self,packet:dict)->dict:
        return {**await super().transcribe(packet),'provider':'twilio-gather'}
class SpeechService:
    def configuration(self)->dict:
        from app.services.stt import SpeechToTextService
        from app.services.banking_vocabulary import BANKING_PHRASES
        return {**SpeechToTextService().readiness(),'browser_mode':settings.browser_stt_mode,'browser_phrase_bias':settings.browser_phrase_bias,'browser_provider':'browser-web-speech','phrases':BANKING_PHRASES,'audio_uploaded':SpeechToTextService().readiness()['audio_available'],'language':settings.voice_language,
            'notice':'Browser Web Speech is the default. Backend audio is used only when explicitly selected or available as a speech-service fallback. Masked transcripts are stored; audio is not retained.',
            'capture':{'end_silence_ms':settings.voice_silence_threshold_ms,'pre_roll_ms':settings.voice_pre_roll_ms,
                'post_roll_ms':settings.voice_post_roll_ms,'start_ms':settings.voice_start_threshold_ms,
                'max_seconds':settings.voice_max_utterance_seconds,'threshold':settings.voice_activity_threshold/32768,
                'echoCancellation':settings.microphone_echo_cancellation,'noiseSuppression':settings.microphone_noise_suppression,
                'autoGainControl':settings.microphone_auto_gain_control}}

class TTSService:
    def payload(self,approved_text:str,enabled:bool)->dict:
        return {'provider':'browser-speech-synthesis','enabled':enabled and settings.enable_tts,'text':approved_text if enabled else ''}
