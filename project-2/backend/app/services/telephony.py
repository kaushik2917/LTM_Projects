from typing import Protocol,Literal
import re
import asyncio
from app.core.config import settings
from urllib.parse import urlsplit

def media_enabled()->bool:
    return settings.app_mode=='real_phone' or settings.telephony_transport=='media'

def public_url_valid(value:str,scheme:str)->bool:
    try:
        parsed=urlsplit(value)
        return parsed.scheme==scheme and bool(parsed.hostname) and parsed.path in {'','/'} and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
    except ValueError:return False

def twilio_client():
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
    return Client(settings.twilio_account_sid,settings.twilio_auth_token,http_client=TwilioHttpClient(timeout=10))

class TelephonyService(Protocol):
    async def receive_call(self,metadata:dict)->dict:...
    async def answer_call(self,call_id:str)->dict:...
    async def stream_audio(self,call_id:str,packet:dict)->dict:...
    async def send_audio(self,call_id:str,text:str)->dict:...
    async def end_call(self,call_id:str)->dict:...
    async def transfer_call(self,call_id:str)->dict:...
    async def get_call_metadata(self,call_id:str)->dict:...
    async def stop_audio(self,call_id:str)->None:...

class MockTelephonyService:
    name='mock'
    async def stop_audio(self,call_id):return None
    async def receive_call(self,metadata):return {'provider':'mock','simulated':True,**metadata}
    async def answer_call(self,call_id):return {'call_id':call_id,'answered':True,'simulated':True}
    async def stream_audio(self,call_id,packet):
        return {'call_id':call_id,'transport':'browser transcript events','packet':packet,'raw_audio_supported':False}
    async def send_audio(self,call_id,text):return {'call_id':call_id,'provider':'browser-speech-synthesis','text':text,'enabled':settings.tts_enabled and settings.enable_tts,'simulated':True}
    async def end_call(self,call_id):return {'call_id':call_id,'ended':True,'simulated':True}
    async def transfer_call(self,call_id):return {'call_id':call_id,'transferred':True,'simulated':True,'message':'Simulated transfer to the demo agent queue; no real phone transfer occurred.'}
    async def get_call_metadata(self,call_id):return {'provider':'mock','call_id':call_id,'real_phone':False,'audio_transport':'browser STT/TTS'}

class TwilioTelephonyService:
    name='twilio'
    async def stop_audio(self,call_id):
        from app.services.media import active_media
        if call_id in active_media:await active_media[call_id].interrupt()
    def __init__(self):
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.public_base_url):
            raise ValueError('Twilio credentials and PUBLIC_BASE_URL are required')
    async def receive_call(self,metadata):return {'provider':'twilio',**metadata}
    async def answer_call(self,call_id):return {'call_id':call_id,'answered_by':'TwiML webhook'}
    async def stream_audio(self,call_id,packet):
        return {'call_id':call_id,'transport':'Media Streams' if media_enabled() else 'Gather','raw_audio_supported':media_enabled()}
    async def send_audio(self,call_id,text):return {'call_id':call_id,'provider':'media-stream' if media_enabled() else 'twilio-say','text':text,'enabled':True,'simulated':False}
    async def end_call(self,provider_id):
        await asyncio.to_thread(lambda:twilio_client().calls(provider_id).update(status='completed'))
        return {'ended':True,'simulated':False}
    async def transfer_call(self,provider_id):
        if not settings.agent_phone_number:
            return {'transferred':False,'simulated':False,'message':'No agent destination configured; call remains with the assistant and the case stays queued.'}
        from twilio.rest import Client
        from twilio.twiml.voice_response import VoiceResponse
        xml=VoiceResponse();xml.say('Connecting you to a support agent.');xml.dial(settings.agent_phone_number)
        await asyncio.to_thread(lambda:twilio_client().calls(provider_id).update(twiml=str(xml)))
        return {'transferred':True,'simulated':False}
    async def get_call_metadata(self,call_id):return {'provider':'twilio','call_id':call_id,'real_phone':True,'audio_transport':'Media Streams' if media_enabled() else 'Gather / Say webhook turns'}

def provider(mode:str)->TelephonyService:
    return TwilioTelephonyService() if mode=='REAL_PHONE_CALL' else MockTelephonyService()

async def native_failure(cid:str)->None:
    from app.database.store import SessionLocal
    from app.services import calls
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse
    with SessionLocal() as db:pid=calls.get_call(db,cid).provider_call_id
    xml=VoiceResponse()
    xml.say('The voice service is temporarily unavailable. Please contact your bank through its verified support channel. Goodbye.')
    xml.hangup()
    await asyncio.to_thread(lambda:twilio_client().calls(pid).update(twiml=str(xml)))
    await calls.end(cid,provider_ended=True,failed=True)

def capabilities()->dict:
    required={'TWILIO_ACCOUNT_SID':bool(re.fullmatch(r'AC[0-9a-fA-F]{32}',settings.twilio_account_sid)),'TWILIO_AUTH_TOKEN':bool(settings.twilio_auth_token),
        'TWILIO_PHONE_NUMBER':bool(re.fullmatch(r'\+[1-9]\d{7,14}',settings.twilio_phone_number)),'PUBLIC_BASE_URL':public_url_valid(settings.public_base_url,'https'),
        'OPERATIONS_TOKEN':bool(settings.admin_api_token)}
    if media_enabled():
        required.update({'PUBLIC_WS_URL':public_url_valid(settings.public_ws_url,'wss'),'STT_PROVIDER=azure':settings.stt_provider=='azure',
            'TTS_PROVIDER=azure':settings.tts_provider=='azure','AZURE_SPEECH_KEY':bool(settings.azure_speech_key),
            'AZURE_SPEECH_REGION':bool(re.fullmatch(r'[a-z0-9-]+',settings.azure_speech_region)),'ENABLE_STT':settings.enable_stt,'ENABLE_TTS':settings.enable_tts})
    missing=[key for key,value in required.items() if not value]
    configured=settings.telephony_provider=='twilio' and not missing
    number=settings.twilio_phone_number
    return {'provider':settings.telephony_provider,'enabled':settings.telephony_provider=='twilio','sdk_available':True,'real_phone_configured':configured,'phone_number':('+'+'*'*max(0,len(number)-5)+number[-4:]) if number else None,
        'missing':missing,'public_url_configured':required['PUBLIC_BASE_URL'],'signature_validation':True,
        'provider_credentials_configured':required['TWILIO_ACCOUNT_SID'] and required['TWILIO_AUTH_TOKEN'],
        'operations_token_configured':required['OPERATIONS_TOKEN'],'phone_number_configured':required['TWILIO_PHONE_NUMBER'],
        'incoming_url':settings.public_base_url.rstrip('/')+'/api/telephony/incoming' if required['PUBLIC_BASE_URL'] else None,
        'status_url':settings.public_base_url.rstrip('/')+'/api/telephony/status' if required['PUBLIC_BASE_URL'] else None,
        'media_url':settings.public_ws_url.rstrip('/')+'/api/telephony/media' if public_url_valid(settings.public_ws_url,'wss') else None,
        'transport':'Twilio Media Streams' if media_enabled() else 'Twilio Gather / Say','raw_audio_streaming':media_enabled(),
        'supported_modes':['REAL_PHONE_CALL','BROWSER_VOICE_DEMO','TEXT_TEST_MODE','MOCK_CALL_MODE'],'transfer_configured':bool(settings.agent_phone_number),
        'silence_timeouts':[settings.silence_first_seconds,settings.silence_second_seconds,settings.silence_end_seconds]}
