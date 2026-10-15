from typing import Literal
from pydantic import BaseModel, Field

class MessageInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source: Literal['text', 'voice'] = 'text'
    stt_ms: float | None = Field(default=None, ge=0, le=3600000)

class CaseUpdate(BaseModel):
    status: Literal['Resolved', 'Needs Follow-up', 'Escalated Further']

class VoiceMetric(BaseModel):
    tts_ms: float = Field(ge=0, le=3600000)
