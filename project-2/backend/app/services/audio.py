"""G.711 mu-law and bounded turn detection. Audio is never written to disk."""
import base64
import io
import math
import wave
import numpy as np
from scipy.signal import resample_poly


class AudioCodecService:
    @staticmethod
    def decode_provider_audio(payload: str) -> bytes:
        raw = base64.b64decode(payload, validate=True)
        if not raw or len(raw) > 8000:
            raise ValueError('Invalid media frame size')
        values = np.bitwise_xor(np.frombuffer(raw, dtype=np.uint8), 255).astype(np.int32)
        magnitude = (((values & 15) << 3) + 132) << ((values >> 4) & 7)
        pcm = np.where(values & 128, 132 - magnitude, magnitude - 132)
        return pcm.astype('<i2').tobytes()

    @staticmethod
    def encode_provider_audio(pcm: bytes) -> str:
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.int32)
        sign = np.where(samples < 0, 128, 0)
        magnitude = np.minimum(np.abs(samples), 32635) + 132
        exponent = np.clip(np.floor(np.log2(magnitude)).astype(np.int32) - 7, 0, 7)
        mantissa = (magnitude >> (exponent + 3)) & 15
        encoded = (~(sign | (exponent << 4) | mantissa) & 255).astype(np.uint8)
        return base64.b64encode(encoded.tobytes()).decode('ascii')

    @staticmethod
    def resample_audio(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
        if source_rate == target_rate:
            return pcm
        divisor = math.gcd(source_rate, target_rate)
        result = resample_poly(np.frombuffer(pcm, dtype='<i2').astype(np.float64), target_rate // divisor, source_rate // divisor)
        return np.clip(np.rint(result), -32768, 32767).astype('<i2').tobytes()

    @classmethod
    def wav_for_stt(cls, pcm: bytes) -> bytes:
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(cls.resample_audio(pcm, 8000, 16000))
        return output.getvalue()


class EndOfTurnDetector:
    """An utterance buffer, never a call controller; sustained speech and pre/post roll."""
    def __init__(self,silence_ms,max_seconds,threshold,sample_rate=8000,pre_roll_ms=300,post_roll_ms=300,start_ms=150):
        self.silence_ms=silence_ms;self.threshold=threshold;self.rate=sample_rate
        self.max_bytes=int(max_seconds*sample_rate*2);self.pre_bytes=int(pre_roll_ms*sample_rate*2/1000)
        self.post_ms=post_roll_ms;self.start_ms=start_ms
        self.buffer=bytearray();self.pre=bytearray();self.silence=0.;self.voice_ms=0.
        self.started=False;self.overflow=False;self.status='LISTENING'
    def active(self,pcm):
        samples=np.frombuffer(pcm,dtype='<i2').astype(np.float64)
        return bool(len(samples) and np.sqrt(np.mean(samples*samples))>=self.threshold)
    def reset(self):
        self.buffer.clear();self.pre.clear();self.silence=self.voice_ms=0.
        self.started=self.overflow=False
    def feed(self,pcm):
        voice=self.active(pcm);duration=len(pcm)*500/self.rate
        self.status='LISTENING'
        if not self.started:
            self.pre.extend(pcm)
            if len(self.pre)>self.pre_bytes+int(self.start_ms*self.rate/500):
                del self.pre[:len(self.pre)-self.pre_bytes-int(self.start_ms*self.rate/500)]
            self.voice_ms=self.voice_ms+duration if voice else 0
            if self.voice_ms<self.start_ms:return None
            self.started=True;self.buffer.extend(self.pre);self.pre.clear();self.status='SPEECH_STARTED'
        elif not self.overflow:self.buffer.extend(pcm)
        self.silence=0 if voice else self.silence+duration
        if voice and self.status!='SPEECH_STARTED':self.status='SPEECH_CONTINUING'
        if not voice:self.status='FINALIZING_UTTERANCE'
        if len(self.buffer)>self.max_bytes:
            self.overflow=True;self.buffer.clear()
        if self.silence<self.silence_ms:return None
        if self.overflow:
            self.reset();self.status='UTTERANCE_TOO_LONG';return None
        trim=max(0,int((self.silence-self.post_ms)*self.rate/500))
        result=bytes(self.buffer[:-trim] if trim else self.buffer)
        self.reset();self.status='UTTERANCE_COMPLETE'
        return result
