import re
import asyncio
from weakref import WeakValueDictionary
from uuid import uuid4
from fastapi import APIRouter,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse,Gather
from app.core.config import settings
from app.database.store import SessionLocal,CallSession
from app.services import calls
from app.services.telephony import capabilities,media_enabled
router=APIRouter(prefix='/api/telephony')
webhook_locks=WeakValueDictionary()

async def signed_form(request:Request)->dict:
    if not capabilities()['real_phone_configured']:raise HTTPException(503,'Real telephony is not configured; use mock call mode')
    from urllib.parse import parse_qsl
    from starlette.datastructures import FormData
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>20000:raise HTTPException(413,'Webhook payload too large')
    if not request.headers.get('content-type','').startswith('application/x-www-form-urlencoded'):
        raise HTTPException(415,'Expected form-encoded webhook')
    try:form=FormData(parse_qsl(body.decode('utf-8'),keep_blank_values=True,max_num_fields=100))
    except (ValueError,UnicodeError):raise HTTPException(422,'Invalid webhook form')
    data={k:str(v) for k,v in form.items()}
    url=settings.public_base_url.rstrip('/')+request.url.path
    if request.url.query:url+='?'+request.url.query
    if not RequestValidator(settings.twilio_auth_token).validate(url,form,request.headers.get('x-twilio-signature','')):
        raise HTTPException(403,'Invalid telephony signature')
    return data

def xml_response(xml)->Response:return Response(str(xml),media_type='application/xml')

def gather_xml(cid:str,text:str)->str:
    with SessionLocal() as db:
        c=calls.get_call(db,cid);token=c.data.get('pending_token') or str(uuid4())
        silence_stage=c.data.get('silence_stage',0)
        wait_seconds=[settings.silence_first_seconds,max(1,settings.silence_second_seconds-settings.silence_first_seconds),max(1,settings.silence_end_seconds-settings.silence_second_seconds)][min(silence_stage,2)]
        c.data={**c.data,'pending_token':token};db.commit()
    action=settings.public_base_url.rstrip('/')+f'/api/telephony/turn/{cid}?token={token}'
    xml=VoiceResponse()
    gather=Gather(input='speech',action=action,method='POST',language=settings.voice_language,speech_timeout='auto',timeout=wait_seconds,action_on_empty_result=True)
    gather.say(text,voice=settings.tts_voice,language=settings.voice_language)
    xml.append(gather)
    return str(xml)

@router.post('/incoming')
async def incoming(request:Request):
    form=await signed_form(request)
    sid=form.get('CallSid','')
    if not re.fullmatch(r'CA[0-9a-fA-F]{32}',sid):raise HTTPException(422,'Invalid call identifier')
    call=await calls.create_call('REAL_PHONE_CALL',provider_id=sid,caller=form.get('From','Phone caller'))
    if call['state'] in calls.TERMINAL:
        xml=VoiceResponse();xml.hangup();return xml_response(xml)
    if media_enabled():
        from secrets import token_urlsafe
        with SessionLocal() as db:
            c=calls.get_call(db,call['id'])
            nonce=c.data.get('media_nonce') or token_urlsafe(32)
            c.data={**c.data,'media_nonce':nonce};db.commit()
        xml=VoiceResponse()
        stream=xml.connect().stream(url=settings.public_ws_url.rstrip('/')+'/api/telephony/media')
        stream.parameter(name='call_id',value=call['id'])
        stream.parameter(name='nonce',value=nonce)
        xml.hangup()
        return xml_response(xml)
    return xml_response(gather_xml(call['id'],calls.GREETING))

@router.get('/health')
def health():
    from sqlalchemy import text
    try:
        with SessionLocal() as db:db.execute(text('SELECT 1'))
        database=True
    except Exception:database=False
    config=capabilities()
    return {**config,'database_available':database,'configured':config['real_phone_configured'],
        'stt_available':bool(settings.azure_speech_key and settings.stt_provider=='azure') if media_enabled() else True,
        'tts_available':bool(settings.azure_speech_key and settings.tts_provider=='azure') if media_enabled() else True}

@router.websocket('/media')
async def media_socket(ws:WebSocket):
    import hmac
    from app.services.media import MediaSession,active_media
    url=settings.public_ws_url.rstrip('/')+'/api/telephony/media'
    # The upgrade is signed against its public HTTPS URL, never a forwarded Host.
    validation_url='https://'+url.removeprefix('wss://')
    if (not media_enabled() or not capabilities()['real_phone_configured'] or
        not RequestValidator(settings.twilio_auth_token).validate(validation_url,{},ws.headers.get('x-twilio-signature',''))):
        await ws.close(code=1008);return
    await ws.accept()
    try:
        connected=await asyncio.wait_for(ws.receive_json(),10)
        if connected.get('event')!='connected':raise ValueError('Expected connection event')
        start=await asyncio.wait_for(ws.receive_json(),10)
        info=start.get('start',{});params=info.get('customParameters',{})
        cid=params.get('call_id','')
        if start.get('event')!='start' or not re.fullmatch(r'MZ[0-9a-fA-F]{32}',start.get('streamSid','')):raise ValueError('Invalid start')
        if info.get('mediaFormat')!={'encoding':'audio/x-mulaw','sampleRate':8000,'channels':1}:raise ValueError('Unsupported audio format')
        with SessionLocal() as db:
            c=calls.get_call(db,cid)
            nonce=c.data.get('media_nonce','')
            if (not nonce or not hmac.compare_digest(nonce,params.get('nonce','')) or c.provider_call_id!=info.get('callSid') or
                info.get('accountSid')!=settings.twilio_account_sid or c.state in calls.TERMINAL or cid in active_media):
                raise ValueError('Invalid call binding')
            c.data={**c.data,'media_nonce':''};db.commit()
        session=MediaSession(ws,cid,start['streamSid'])
        active_media[cid]=session
        await calls.event(cid,'media_connected',{'transport':'bidirectional','codec':'mulaw/8000'})
        await session.run()
    except (ValueError,TypeError,AttributeError,HTTPException,TimeoutError,WebSocketDisconnect):
        from contextlib import suppress
        with suppress(Exception):await ws.close(code=1008)

@router.post('/turn/{cid}')
async def phone_turn(cid:str,request:Request,token:str):
    async with webhook_locks.setdefault(cid,asyncio.Lock()):
        return await _phone_turn(cid,request,token)

async def _phone_turn(cid:str,request:Request,token:str):
    form=await signed_form(request)
    with SessionLocal() as db:
        c=calls.get_call(db,cid)
        if c.provider_call_id!=form.get('CallSid'):raise HTTPException(403,'Call identifier mismatch')
        cached=c.data.get('webhook_responses',{}).get(token)
        if cached:return xml_response(cached)
        if c.data.get('pending_token')!=token:raise HTTPException(409,'Stale phone turn')
    current=calls.detail(cid)
    if current['state'] in calls.TERMINAL:
        xml=VoiceResponse();xml.hangup();return xml_response(xml)
    transcript=form.get('SpeechResult','').strip()
    output=None
    if not transcript:
        silence=await calls.silence_check(cid,True)
        if silence and silence.get('final'):
            xml=VoiceResponse();xml.say(silence['text']);xml.hangup();output=str(xml)
        else:reply=silence['text'] if silence else 'How may I help you?'
    else:
        # Explicitly fictional phone verification; never a real OTP/PIN challenge.
        match=re.search(r'\bdemo (?:customer|profile)(?: id)?\s+(CSB\d{5})\b',transcript,re.I)
        if match:
            from app.services.core_banking import core_banking
            try:
                profile=core_banking.get_customer(match.group(1).upper())
                with SessionLocal() as db:
                    c=calls.get_call(db,cid);c.customer_id=profile['id'];c.authentication_status='PARTIALLY_VERIFIED';c.data={**c.data,'voice_demo_challenge':True};db.commit()
                reply='What is the verification colour registered for this account? Please do not share a PIN, password or one-time code.'
                await calls.event(cid,'authentication',{'status':'PARTIALLY_VERIFIED','customer_id':profile['id'],'synthetic':True})
            except ValueError:reply='I could not locate that account profile. I can still help with general banking questions.'
        elif current.get('voice_demo_challenge'):
            answer=transcript.lower().strip(' .')
            updated=await calls.verify_demo(cid,current['customer_id'],answer)
            success=updated['authentication_status']=='VERIFIED'
            with SessionLocal() as db:
                c=calls.get_call(db,cid);c.data={**c.data,'voice_demo_challenge':not success};db.commit()
            reply='The identity check is complete. What account information would you like?' if success else 'That did not match the identity check. We can try again or continue with general information.'
        else:
            try:
                turn=await calls.call_turn(cid,transcript,'voice',request_id=token,stt_confidence=float(form['Confidence']) if form.get('Confidence','').replace('.','',1).isdigit() and 0<=float(form['Confidence'])<=1 else None)
            except HTTPException as exc:
                if exc.status_code!=503:raise
                reply=settings.ai_failure_text
            else:
                reply=turn['voice_response']
                if turn['decision']=='ESCALATE' and settings.agent_phone_number:
                    xml=VoiceResponse();xml.say(reply,voice=settings.tts_voice,language=settings.voice_language)
                    xml.dial(settings.agent_phone_number,action=settings.public_base_url.rstrip('/')+f'/api/telephony/dial-ended/{cid}')
                    output=str(xml)
                    await calls.event(cid,'transfer_requested',{'provider':'twilio','destination_configured':True})
                else:await calls.state(cid,'WAITING',True)
    with SessionLocal() as db:
        c=calls.get_call(db,cid);c.data={**c.data,'pending_token':str(uuid4())};db.commit()
    output=output or gather_xml(cid,reply)
    with SessionLocal() as db:
        c=calls.get_call(db,cid);cache={**c.data.get('webhook_responses',{}),token:output};c.data={**c.data,'webhook_responses':dict(list(cache.items())[-10:])};db.commit()
    return xml_response(output)

@router.post('/status')
async def status(request:Request):
    form=await signed_form(request)
    with SessionLocal() as db:c=db.scalar(select(CallSession).where(CallSession.provider_call_id==form.get('CallSid')));cid=c.id if c else None
    if not cid:raise HTTPException(404,'Call not found')
    provider_status=form.get('CallStatus','')
    if provider_status in {'completed','failed','busy','no-answer','canceled'}:await calls.end(cid,provider_ended=True,failed=provider_status!='completed')
    else:await calls.event(cid,'provider_status',{'status':provider_status})
    return {'ok':True}

@router.post('/dial-ended/{cid}')
async def dial_ended(cid:str,request:Request):
    form=await signed_form(request)
    with SessionLocal() as db:
        if calls.get_call(db,cid).provider_call_id!=form.get('CallSid'):raise HTTPException(403,'Call mismatch')
    await calls.event(cid,'transfer_result',{'status':form.get('DialCallStatus','unknown')})
    await calls.end(cid,provider_ended=True)
    xml=VoiceResponse();xml.say('Thank you for calling.');xml.hangup();return xml_response(xml)
