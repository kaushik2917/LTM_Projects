from pathlib import Path
from typing import Literal
from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings,SettingsConfigDict
ROOT=Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=ROOT/'.env',env_file_encoding='utf-8-sig',extra='ignore')
    mock_mode:bool=True
    app_mode:str='mock'
    llm_provider:str='ollama'
    llm_model:str='llama3.2'
    ollama_url:str='http://localhost:11434'
    database_url:str=f'sqlite:///{(ROOT/"data/callsense.db").as_posix()}'
    tts_enabled:bool=True
    enable_tts:bool=True
    rag_top_k:int=Field(default=5,ge=1,le=15)
    embedding_model:str='local-lsa-128'
    whisper_model:str='base.en'
    whisper_device:str='auto'
    whisper_compute_type:str='int8'
    whisper_download_root:str=str(ROOT/'models/whisper')
    stt_fallback_provider:str='browser'
    stt_low_confidence_threshold:float=Field(default=.65,ge=0,le=1)
    customer_show_demo_language:bool=False
    voice_pre_roll_ms:int=Field(default=300,ge=0,le=1000)
    voice_post_roll_ms:int=Field(default=300,ge=0,le=1000)
    voice_start_threshold_ms:int=Field(default=150,ge=60,le=500)
    microphone_echo_cancellation:bool=True
    microphone_noise_suppression:bool=True
    microphone_auto_gain_control:bool=True
    stt_provider:str='browser'
    stt_model:str='web-speech'
    browser_stt_mode:Literal['browser','backend']='browser'
    browser_phrase_bias:bool=False
    tts_provider:str='browser'
    tts_voice:str='alice'
    voice_language:str='en-IN'
    telephony_provider:Literal['mock','twilio']='mock'
    twilio_account_sid:str=''
    twilio_auth_token:str=''
    twilio_phone_number:str=''
    public_base_url:str=''
    agent_phone_number:str=Field(default='',validation_alias=AliasChoices('HUMAN_AGENT_NUMBER','agent_phone_number'))
    admin_api_token:str=Field(default='',validation_alias=AliasChoices('OPERATIONS_TOKEN','admin_api_token'))
    public_ws_url:str=''
    telephony_transport:Literal['gather','media']='gather'
    azure_speech_key:str=''
    azure_speech_region:str=''
    azure_speech_voice:str='en-IN-NeerjaNeural'
    enable_stt:bool=True
    enable_call_recording:bool=False
    call_greeting_text:str="Welcome to Call Sense Bank. I'm the Call Sense AI banking assistant. How may I help you today?"
    voice_silence_threshold_ms:int=Field(default=1200,ge=800,le=5000,validation_alias=AliasChoices('VOICE_END_SILENCE_MS','voice_silence_threshold_ms'))
    voice_max_utterance_seconds:int=Field(default=60,ge=2,le=120)
    voice_activity_threshold:int=Field(default=500,ge=100,le=10000)
    stt_failure_text:str="I'm sorry, I couldn't hear that clearly. Could you repeat it?"
    ai_failure_text:str="I'm having trouble processing that request. Please try once more."
    enable_pii_redaction:bool=True
    enable_injection_guard:bool=True
    silence_first_seconds:int=Field(default=30,ge=3,validation_alias=AliasChoices('CALL_INITIAL_SILENCE_SECONDS','silence_first_seconds'))
    silence_second_seconds:int=Field(default=90,ge=5,validation_alias=AliasChoices('CALL_REPROMPT_SECONDS','silence_second_seconds'))
    silence_end_seconds:int=Field(default=180,ge=10,validation_alias=AliasChoices('CALL_END_SILENCE_SECONDS','silence_end_seconds'))
    silence_final_action:Literal['continue','reprompt']='continue'
    max_call_duration_minutes:float=Field(default=0,ge=0)

    @field_validator('silence_final_action',mode='before')
    @classmethod
    def migrate_silence_action(cls,value):
        # Old local configuration must not silently restore idle hangups.
        return 'continue' if value in {'end','transfer'} else value

    cors_origins:str='http://localhost:5173,http://127.0.0.1:5173'
settings=Settings()
