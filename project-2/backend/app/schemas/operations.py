from typing import Literal
from pydantic import BaseModel,Field

class CallCreate(BaseModel):
    mode:Literal['REAL_PHONE_CALL','BROWSER_VOICE_DEMO','TEXT_TEST_MODE','MOCK_CALL_MODE']='MOCK_CALL_MODE'
    customer_id:str|None=None
class SpeechAlternative(BaseModel):
    text:str=Field(max_length=2000)
    confidence:float|None=Field(default=None,ge=0,le=1)
class CallMessage(BaseModel):
    stt_confidence:float|None=Field(default=None,ge=0,le=1)
    stt_alternatives:list[SpeechAlternative]=Field(default_factory=list,max_length=5)
    text:str=Field(min_length=1,max_length=2000)
    source:Literal['text','voice']='text'
    stt_ms:float|None=Field(default=None,ge=0,le=3600000)
    speech_end_ms:float|None=Field(default=None,ge=0,le=3600000)
    request_id:str|None=Field(default=None,max_length=80)
class DemoVerify(BaseModel):
    customer_id:str=Field(pattern=r'^CSB\d{5}$')
    answer:str=Field(min_length=1,max_length=40)
class ClientState(BaseModel):
    turn_count:int|None=Field(default=None,ge=0)
    state:Literal['LISTENING','SPEAKING','WAITING','TRANSCRIBING','CUSTOMER_SPEAKING','FINALIZING_UTTERANCE']
class ArticleInput(BaseModel):
    title:str=Field(min_length=4,max_length=160)
    category:str=Field(min_length=2,max_length=50)
    content:str=Field(min_length=80,max_length=16000)
    supported_intents:list[str]=Field(default_factory=list,max_length=30)
    keywords:list[str]=Field(default_factory=list,max_length=40)
    source_type:Literal['GENERAL_BANKING_INFORMATION','BANK_POLICY']='BANK_POLICY'
    risk_level:Literal['LOW','MEDIUM','HIGH']='LOW'
    approved:bool=True
    enabled:bool=True
class RetrievalInput(BaseModel):
    query:str=Field(min_length=1,max_length=2000)
class GapReview(BaseModel):
    status:Literal['Open','Reviewed','Resolved']
