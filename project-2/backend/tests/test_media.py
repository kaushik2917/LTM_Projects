import asyncio
import base64
import json
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock
from fastapi import HTTPException
import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator
from app.core.config import settings
from app.services.audio import AudioCodecService as Codec, EndOfTurnDetector
from app.services import calls
from app.services.telephony import capabilities


@pytest.fixture
def media_config(monkeypatch):
    values = {'app_mode':'real_phone','telephony_provider':'twilio','twilio_account_sid':'AC'+'c'*32,
              'twilio_auth_token':'fixture-signing-secret','twilio_phone_number':'+15005550006',
              'public_base_url':'https://voice.example.test','public_ws_url':'wss://voice.example.test',
              'admin_api_token':'fixture-operator-secret','stt_provider':'azure','tts_provider':'azure',
              'azure_speech_key':'fixture-speech-secret','azure_speech_region':'eastus'}
    for key, value in values.items():monkeypatch.setattr(settings,key,value)
    # No automated test may perform a telephone REST request.
    monkeypatch.setattr('twilio.rest.Client',lambda *a,**k:pytest.fail('Unexpected Twilio network request'))
    return values


def signed(client,path,data):
    signature=RequestValidator(settings.twilio_auth_token).compute_signature(settings.public_base_url+path,data)
    return client.post(path,data=data,headers={'X-Twilio-Signature':signature})


def new_call(client,suffix='d'):
    sid='CA'+suffix*32
    response=signed(client,'/api/telephony/incoming',{'CallSid':sid,'From':'+15005550009'})
    assert response.status_code==200,response.text
    stream=ET.fromstring(response.text).find('Connect/Stream')
    assert stream.attrib['url'].startswith('wss://')
    return sid,{item.attrib['name']:item.attrib['value'] for item in stream.findall('Parameter')}


def start_socket(client,sid,params):
    signature=RequestValidator(settings.twilio_auth_token).compute_signature(settings.public_base_url+'/api/telephony/media',{})
    return client.websocket_connect('/api/telephony/media',headers={'X-Twilio-Signature':signature})


def handshake(ws,sid,params):
    ws.send_json({'event':'connected','protocol':'Call','version':'1.0.0'})
    ws.send_json({'event':'start','streamSid':'MZ'+'e'*32,'start':{'callSid':sid,'accountSid':settings.twilio_account_sid,
        'customParameters':params,'mediaFormat':{'encoding':'audio/x-mulaw','sampleRate':8000,'channels':1}}})


def finish_playback(ws):
    count=0
    while True:
        message=ws.receive_json()
        if message['event']=='media':
            assert base64.b64decode(message['media']['payload'])
            count+=1
        if message['event']=='mark':
            ws.send_json(message)
            return count


def utterance(ws):
    tone=(np.sin(np.arange(160)*2*np.pi*440/8000)*6000).astype('<i2').tobytes()
    for pcm in [tone]*12+[bytes(320)]*65:
        ws.send_json({'event':'media','streamSid':'MZ'+'e'*32,'media':{'track':'inbound','payload':Codec.encode_provider_audio(pcm)}})


def test_codec_known_vectors_and_resampling():
    assert Codec.decode_provider_audio(base64.b64encode(bytes([255,127,128,0])).decode()) == np.array([0,0,32124,-32124],dtype='<i2').tobytes()
    samples=np.array([0,1000,-1000,16000,-16000],dtype='<i2')
    result=np.frombuffer(Codec.decode_provider_audio(Codec.encode_provider_audio(samples.tobytes())),dtype='<i2')
    assert np.max(np.abs(samples.astype(int)-result))<400
    assert len(Codec.resample_audio(bytes(16000),8000,16000))==32000
    assert Codec.wav_for_stt(bytes(320)).startswith(b'RIFF')
    with pytest.raises(ValueError):Codec.decode_provider_audio('bad!')


def test_turn_detector_boundaries():
    detector=EndOfTurnDetector(700,2,500)
    silence=bytes(320)
    voice=np.full(160,3000,dtype='<i2').tobytes()
    for _ in range(100):assert detector.feed(silence) is None
    for _ in range(10):assert detector.feed(voice) is None
    for _ in range(34):assert detector.feed(silence) is None
    assert detector.feed(silence)
    assert not detector.buffer
    results=[detector.feed(voice) for _ in range(100)]
    assert not any(results)
    for _ in range(35):assert detector.feed(silence) is None
    assert detector.status=='UTTERANCE_TOO_LONG'


def test_readiness_no_secrets(client,media_config,monkeypatch):
    result=client.get('/api/telephony/health')
    assert result.json()['configured']
    for key in ['twilio_auth_token','admin_api_token','azure_speech_key']:
        assert getattr(settings,key) not in result.text
    assert settings.twilio_phone_number not in result.text
    monkeypatch.setattr(settings,'azure_speech_key','')
    assert 'AZURE_SPEECH_KEY' in capabilities()['missing']
    assert not capabilities()['real_phone_configured']


def test_invalid_signatures_and_call_binding(client,media_config):
    assert client.post('/api/telephony/incoming',data={'CallSid':'CA'+'d'*32}).status_code==403
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/telephony/media'):pass
    sid,params=new_call(client,'1')
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,{**params,'nonce':'wrong'})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    asyncio.run(calls.end(params['call_id'],provider_ended=True))


def test_two_turn_audio_context_and_hangup(client,media_config,monkeypatch):
    transcripts=iter(["My debit card isn't working.",'Online.'])
    class Speech:
        async def transcribe(self,pcm):
            assert len(pcm)>1000
            return {'text':next(transcripts),'detected_language':'en-IN','confidence':0.97,'transcription_latency_ms':12}
        async def generate_audio(self,text):
            assert text
            return np.full(160,1200,dtype='<i2').tobytes()
    monkeypatch.setattr('app.services.media.audio_speech_provider',Speech)
    sid,params=new_call(client)
    cid=params['call_id']
    assert 'media_nonce' not in calls.detail(cid)
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,params)
        assert finish_playback(ws)
        utterance(ws)
        assert finish_playback(ws)
        utterance(ws)
        assert finish_playback(ws)
        ws.send_json({'event':'stop','streamSid':'MZ'+'e'*32})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    result=calls.detail(cid)
    assert result['state']=='COMPLETED' and result['ended_at']
    assert len(result['turns'])==2
    assert result['turns'][1]['context_used']
    assert result['turns'][1]['prediction']['intent']=='card_payment_issue'
    assert result['turns'][0]['speech_metadata']['confidence']==0.97
    assert result['turns'][0]['latency']['tts_ms'] is not None
    from app.services.media import active_media
    assert cid not in active_media


def test_operator_session_and_csrf(client,media_config):
    client.cookies.clear()
    assert client.get('/api/calls').status_code==401
    origin={'Origin':'http://localhost:5173'}
    assert client.post('/api/auth/session',json={'token':'wrong'},headers=origin).status_code==401
    response=client.post('/api/auth/session',json={'token':settings.admin_api_token},headers=origin)
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert settings.admin_api_token not in response.text
    assert client.get('/api/calls').status_code==200
    assert client.post('/api/calls',json={'mode':'MOCK_CALL_MODE'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.delete('/api/auth/session',headers=origin).status_code==200
    assert client.get('/api/calls').status_code==401
    client.cookies.clear()


def test_transfer_provider_failure_safe(client,media_config,monkeypatch):
    sid,params=new_call(client,'2')
    from app.services.telephony import TwilioTelephonyService
    monkeypatch.setattr(TwilioTelephonyService,'transfer_call',AsyncMock(side_effect=RuntimeError('private provider detail')))
    with pytest.raises(HTTPException) as error:asyncio.run(calls.transfer(params['call_id']))
    assert error.value.status_code==503
    assert 'private provider detail' not in json.dumps(calls.detail(params['call_id']))
    assert calls.detail(params['call_id'])['state'] not in calls.TERMINAL
    asyncio.run(calls.end(params['call_id'],provider_ended=True))


def test_barge_in_clears_playback_and_redacts_otp(client,media_config,monkeypatch):
    class Speech:
        async def transcribe(self,pcm):
            return {'text':'My OTP is 526344.','detected_language':'en-IN','confidence':None,'transcription_latency_ms':1}
        async def generate_audio(self,text):
            return bytes(16000 if text==settings.call_greeting_text else 320)
    monkeypatch.setattr('app.services.media.audio_speech_provider',Speech)
    sid,params=new_call(client,'3')
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,params)
        assert ws.receive_json()['event']=='media'
        utterance(ws)
        while ws.receive_json()['event']!='clear':pass
        assert finish_playback(ws)
        ws.send_json({'event':'stop','streamSid':'MZ'+'e'*32})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    result=calls.detail(params['call_id'])
    assert '526344' not in json.dumps(result)
    assert any(e['type']=='interrupt' for e in result['events'])
    assert result['turns'][0]['privacy']['redacted']


def test_repeated_speech_failure_exhausts_fallback_then_fails(client,media_config,monkeypatch):
    spoken=[]
    class Speech:
        async def transcribe(self,pcm):raise RuntimeError('private speech service detail')
        async def generate_audio(self,text):
            spoken.append(text)
            return bytes(320)
    monkeypatch.setattr('app.services.media.audio_speech_provider',Speech)
    from app.services.telephony import TwilioTelephonyService
    ending=AsyncMock(return_value={'ended':True})
    monkeypatch.setattr(TwilioTelephonyService,'end_call',ending)
    sid,params=new_call(client,'4')
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,params)
        finish_playback(ws)
        for _ in range(2):
            utterance(ws)
            finish_playback(ws)
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    assert settings.stt_failure_text in spoken
    ending.assert_awaited_once_with(sid)
    result=calls.detail(params['call_id'])
    assert result['state']=='FAILED'
    assert 'private speech service detail' not in json.dumps(result)


def test_upi_spoken_amount_and_followup(client):
    from app.services.pipeline import process
    first=asyncio.run(process("I sent five thousand rupees using UPI yesterday, but the receiver hasn't received it.",[]))
    assert first['entities']['amount']==5000
    assert first['entities']['currency']=='INR'
    assert first['entities']['payment_channel']=='UPI'
    assert first['entities']['dates']==['yesterday']
    assert first['decision']=='CLARIFY' and first['awaiting_slot']=='payment_status'
    second=asyncio.run(process('It says successful.',[first]))
    assert second['context_used']
    assert second['awaiting_slot'] is None
    assert second['prediction']['intent']==first['prediction']['intent']
    fraud=asyncio.run(process("I don't recognize a fifteen-thousand-rupee card transaction.",[]))
    assert fraud['risk']=='HIGH' and fraud['decision']=='ESCALATE' and fraud['handoff']
    assert fraud['entities']['amount']==15000


def test_config_missing_and_local_mode_never_calls_provider(client,monkeypatch):
    monkeypatch.setattr(settings,'app_mode','real_phone')
    monkeypatch.setattr(settings,'telephony_provider','twilio')
    monkeypatch.setattr(settings,'twilio_auth_token','')
    assert not capabilities()['real_phone_configured']
    assert client.post('/api/telephony/incoming',data={}).status_code==503
    monkeypatch.setattr(settings,'app_mode','mock')
    monkeypatch.setattr(settings,'telephony_provider','mock')
    monkeypatch.setattr('twilio.rest.Client',lambda *a,**k:pytest.fail('Mock mode contacted Twilio'))
    response=client.post('/api/calls',json={'mode':'MOCK_CALL_MODE'})
    assert response.status_code==201
    assert client.post('/api/calls/'+response.json()['id']+'/end').status_code==200

def test_transient_speech_failures_recover_same_stream(client,media_config,monkeypatch):
    attempts={'stt':0,'tts':0}
    class Speech:
        async def transcribe(self,pcm):
            attempts['stt']+=1
            if attempts['stt']==1:raise RuntimeError('temporary STT')
            return {'text':'What is NEFT?','transcription_latency_ms':1}
        async def generate_audio(self,text):
            attempts['tts']+=1
            if attempts['tts']==1:raise RuntimeError('temporary TTS')
            return bytes(320)
    monkeypatch.setattr('app.services.media.audio_speech_provider',Speech)
    sid,params=new_call(client,'8');cid=params['call_id']
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,params);finish_playback(ws)
        utterance(ws);finish_playback(ws)
        assert calls.detail(cid)['ended_at'] is None
        utterance(ws);finish_playback(ws)
        assert len(calls.detail(cid)['turns'])==1
        assert calls.detail(cid)['ended_at'] is None
        ws.send_json({'event':'stop','streamSid':'MZ'+'e'*32})
        with pytest.raises(WebSocketDisconnect):ws.receive_json()
    assert calls.detail(cid)['termination_reason']=='provider_hangup'

@pytest.mark.parametrize('configured',[False,True])
def test_explicit_human_media_handoff(client,media_config,monkeypatch,configured):
    monkeypatch.setattr(settings,'agent_phone_number','+15005550007' if configured else '')
    spoken=[]
    class Speech:
        async def transcribe(self,pcm):return {'text':'Transfer the call to a human agent.','confidence':.95,'transcription_latency_ms':1}
        async def generate_audio(self,text):spoken.append(text);return bytes(320)
    monkeypatch.setattr('app.services.media.audio_speech_provider',Speech)
    from app.services.telephony import TwilioTelephonyService
    transfer=AsyncMock(return_value={'transferred':True,'simulated':False})
    monkeypatch.setattr(TwilioTelephonyService,'transfer_call',transfer)
    sid,params=new_call(client,'5' if configured else '6');cid=params['call_id']
    with start_socket(client,sid,params) as ws:
        handshake(ws,sid,params);finish_playback(ws)
        utterance(ws);finish_playback(ws)
        if configured:
            with pytest.raises(WebSocketDisconnect):ws.receive_json()
        else:
            assert calls.detail(cid)['ended_at'] is None
            ws.send_json({'event':'stop','streamSid':'MZ'+'e'*32})
            with pytest.raises(WebSocketDisconnect):ws.receive_json()
    c=calls.detail(cid);t=c['turns'][0]
    assert t['risk']=='LOW' and t['handoff']['customer_requested_human']
    assert all('suspicious' not in x for x in spoken)
    if configured:
        transfer.assert_awaited_once_with(sid)
        assert c['state']=='TRANSFERRED'
        assert any("I'll connect" in x for x in spoken)
    else:
        transfer.assert_not_awaited()
        assert any('support queue' in x for x in spoken)
