import asyncio
from datetime import datetime,timezone
from weakref import WeakValueDictionary
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.database.store import SessionLocal,CallSession,CallEvent,Conversation,Turn,Escalation,AuthenticationEvent,now
from app.services.pipeline import process
from app.services.handoff import escalation_response
from app.services.core_banking import core_banking
from app.services.telephony import provider
from app.services.speech import BrowserSTTProvider,TwilioSTTProvider
from app.services.rag import record_gap
from app.services.privacy import redact
from app.core.config import settings
from app.services.termination import CallTerminationController

STATES=['CUSTOMER_SPEAKING','FINALIZING_UTTERANCE','RINGING','CONNECTED','LISTENING','TRANSCRIBING','UNDERSTANDING','RETRIEVING','GENERATING','VERIFYING','RESPONDING','SPEAKING','WAITING','ESCALATING','TRANSFERRED','COMPLETED','FAILED']
TERMINAL={'TRANSFERRED','COMPLETED','FAILED'}
GREETING=settings.call_greeting_text
locks=WeakValueDictionary()
subscribers:set[asyncio.Queue]=set()

def get_call(db,cid):
    c=db.get(CallSession,cid)
    if not c:raise HTTPException(404,'Call not found')
    return c

def serialize(c:CallSession)->dict:
    end=datetime.fromisoformat(c.ended_at) if c.ended_at else datetime.now(timezone.utc)
    return {'id':c.id,'conversation_id':c.conversation_id,'created_at':c.created_at,'ended_at':c.ended_at,'state':c.state,'mode':c.mode,
            'provider':'twilio' if c.mode=='REAL_PHONE_CALL' else 'mock','provider_call_id':c.provider_call_id,
            'customer_id':c.customer_id,'authentication_status':c.authentication_status,'duration_seconds':max(0,round((end-datetime.fromisoformat(c.created_at)).total_seconds())),**{k:v for k,v in c.data.items() if k!='media_nonce'}}

async def publish(event:dict):
    for queue in list(subscribers):
        if queue.full():
            try:queue.get_nowait()
            except asyncio.QueueEmpty:pass
        queue.put_nowait(event)

def list_calls()->list[dict]:
    with SessionLocal() as db:return [serialize(c) for c in db.scalars(select(CallSession).order_by(CallSession.created_at.desc()))]

def detail(cid:str)->dict:
    with SessionLocal() as db:
        c=get_call(db,cid)
        events=[{'id':e.id,'created_at':e.created_at,'type':e.event_type,**e.data} for e in db.scalars(select(CallEvent).where(CallEvent.call_id==cid).order_by(CallEvent.created_at))]
        turns=[{'id':t.id,'created_at':t.created_at,**t.data} for t in db.scalars(select(Turn).where(Turn.conversation_id==c.conversation_id).order_by(Turn.created_at))]
        return {**serialize(c),'events':events,'turns':turns}

async def event(cid:str,kind:str,data:dict):
    with SessionLocal() as db:
        db.add(CallEvent(call_id=cid,event_type=kind,data=data));db.commit()
    await publish({'type':kind,'call_id':cid,'data':data})

async def state(cid:str,value:str,touch:bool=False):
    if value not in STATES:raise HTTPException(422,'Unknown call state')
    with SessionLocal() as db:
        c=get_call(db,cid)
        if c.state in TERMINAL and c.state!=value:return
        c.state=value
        if touch:c.data={**c.data,'last_activity':now(),'silence_stage':0}
        db.add(CallEvent(call_id=cid,event_type='state',data={'state':value}));db.commit();snapshot=serialize(c)
    await publish({'type':'state','call_id':cid,'data':snapshot})

async def create_call(mode:str,customer_id:str|None=None,provider_id:str|None=None,caller:str='Demo caller')->dict:
    if customer_id:
        try:core_banking.get_customer(customer_id)
        except ValueError:raise HTTPException(404,'Demo customer not found')
    with SessionLocal() as db:
        if provider_id:
            existing=db.scalar(select(CallSession).where(CallSession.provider_call_id==provider_id))
            if existing:return serialize(existing)
        conversation=Conversation();db.add(conversation);db.flush()
        c=CallSession(conversation_id=conversation.id,mode=mode,customer_id=customer_id,provider_call_id=provider_id,
            authentication_status='PARTIALLY_VERIFIED' if customer_id else 'UNVERIFIED',
            data={'caller':redact(caller)[0],'last_activity':now(),'silence_stage':0,'greeting':GREETING,'turn_count':0,'summary':None,'ever_escalated':False,'pending_token':str(uuid4())})
        db.add(c);db.commit();cid=c.id
    await event(cid,'state',{'state':'RINGING'})
    await provider(mode).receive_call({'call_id':cid})
    await provider(mode).answer_call(cid)
    await state(cid,'CONNECTED');await event(cid,'greeting',{'text':GREETING});await state(cid,'WAITING',True)
    return detail(cid)

async def verify_demo(cid:str,customer_id:str,answer:str)->dict:
    async with locks.setdefault(cid,asyncio.Lock()):
        p=core_banking.get_customer(customer_id)
        with SessionLocal() as db:
            c=get_call(db,cid)
            if c.state in TERMINAL:raise HTTPException(409,'Call is no longer active')
            tries=c.data.get('verification_attempts',0)
            if tries>=5:raise HTTPException(429,'Demo verification attempt limit reached; start a new demo call')
            success=answer.strip().lower()==p['demo_answer']
            c.customer_id=customer_id;c.authentication_status='VERIFIED' if success else 'PARTIALLY_VERIFIED'
            c.data={**c.data,'verification_attempts':tries+1,'last_activity':now(),'silence_stage':0}
            db.add(AuthenticationEvent(call_id=cid,status=c.authentication_status,data={'customer_id':customer_id,'synthetic':True,'success':success}));db.commit();snapshot=serialize(c)
        await event(cid,'authentication',{'status':snapshot['authentication_status'],'customer_id':customer_id,'synthetic':True})
        return snapshot

async def call_turn(cid:str,text:str,source:str='text',stt_ms:float|None=None,speech_end_ms:float|None=None,request_id:str|None=None,stt_confidence:float|None=None,stt_alternatives:list|None=None,speech_metadata:dict|None=None)->dict:
    async with locks.setdefault(cid,asyncio.Lock()):
        current=detail(cid)
        if not text.strip() or len(text)>2000:raise HTTPException(422,'Transcript must contain 1-2000 characters')
        if current['state'] in TERMINAL:raise HTTPException(409,'Call is no longer active')
        if request_id:
            old=next((t for t in current['turns'] if t.get('request_id')==request_id),None)
            if old:return old
        await state(cid,'TRANSCRIBING',True)
        speech=TwilioSTTProvider() if current['mode']=='REAL_PHONE_CALL' else BrowserSTTProvider()
        transcript=await speech.transcribe({'text':text,'source':source,'stt_ms':stt_ms})
        try:
            result=await process(transcript['text'],current['turns'],source,stt_ms,{'customer_id':current['customer_id'],'authentication_status':current['authentication_status']},lambda s:state(cid,s),speech_metadata or {'confidence':stt_confidence,'alternatives':stt_alternatives or [],'provider':'browser' if source=='voice' else 'text'})
            result['latency']['speech_end_ms']=speech_end_ms
            result['request_id']=request_id
            result['call_id']=cid
            if current['mode']=='REAL_PHONE_CALL':
                if result['decision']=='VERIFY':
                    result['voice_response']="For account-specific information, your identity needs to be verified through your bank's secure channel. I can explain the process or help you reach support. Never share your PIN, OTP, password or CVV."
                elif result['decision']=='ESCALATE':
                    answer=escalation_response(result['escalation_reason'],result['prediction'].get('genuine_security',False),bool(settings.agent_phone_number))
                    result.update(answer=answer,display_response=answer,voice_response=answer)
                    result['handoff'].update(handoff_mode='telephone' if settings.agent_phone_number else 'queue',simulated=not bool(settings.agent_phone_number))
            if result['handoff']:
                result['handoff'].update({'call_id':cid,'masked_caller':current.get('caller'),'customer_id':current['customer_id'],'authentication_status':current['authentication_status'],'mode':current['mode'],'customer_profile':{'id':current['customer_id'],'synthetic':True},'steps_already_attempted':[e['data'] if 'data' in e else e for e in current['events'] if e['type']=='demo_card_block']})
            with SessionLocal() as db:
                c=get_call(db,cid)
                t=Turn(conversation_id=c.conversation_id,data=result);db.add(t);db.flush()
                if result['handoff']:db.add(Escalation(conversation_id=c.conversation_id,turn_id=t.id,packet=result['handoff']))
                c.data={**c.data,'last_activity':now(),'silence_stage':0,'turn_count':current['turn_count']+1,'latest':result,
                        'ever_escalated':current.get('ever_escalated',False) or result['decision']=='ESCALATE'}
                db.commit();response={'id':t.id,'created_at':t.created_at,**result}
            record_gap(result)
            response['speech']=await provider(current['mode']).send_audio(cid,result['voice_response'])
            await publish({'type':'turn','call_id':cid,'data':response})
            await state(cid,'ESCALATING' if result['decision']=='ESCALATE' else 'SPEAKING')
            return response
        except HTTPException:raise
        except Exception:
            await event(cid,'error',{'message':'The turn failed safely; no unverified answer was released.'})
            await state(cid,'WAITING',True)
            raise HTTPException(503,'The turn could not be completed. Retry or ask an agent.')

async def interrupt(cid:str)->dict:
    current=detail(cid)
    if current['state'] in TERMINAL:raise HTTPException(409,'Call is no longer active')
    await provider(current['mode']).stop_audio(cid)
    await event(cid,'interrupt',{'action':'cancel_tts','note':'Playback interruption requested.'})
    await state(cid,'LISTENING',True)
    return {'interrupted':True}

async def transfer(cid:str)->dict:
    async with locks.setdefault(cid,asyncio.Lock()):
        current=detail(cid)
        if current['state'] in TERMINAL:raise HTTPException(409,'Call is no longer active')
        with SessionLocal() as db:c=get_call(db,cid);provider_id=c.provider_call_id
        await state(cid,'ESCALATING')
        try:result=await provider(current['mode']).transfer_call(provider_id or cid)
        except Exception:
            await event(cid,'transfer_error',{'message':'Provider transfer failed; the call remains with the assistant.'})
            await state(cid,'LISTENING',True)
            raise HTTPException(503,'Provider transfer failed; try again or use the support queue')
        await event(cid,'transfer',result)
        if result.get('transferred'):
            await _finish(cid,'TRANSFERRED','transfer')
        return result

async def _finish(cid:str,final_state:str,reason:str):
    CallTerminationController.validate(reason)
    with SessionLocal() as db:
        c=get_call(db,cid)
        if c.state in TERMINAL:return
        c.state=final_state;c.ended_at=now()
        c.data={**c.data,'termination_reason':reason}
        conversation=db.get(Conversation,c.conversation_id);conversation.status='closed'
        ts=list(db.scalars(select(Turn).where(Turn.conversation_id==c.conversation_id).order_by(Turn.created_at)))
        c.data={**c.data,'summary':' | '.join(t.data['query']+' -> '+t.data['decision'] for t in ts[-5:]) or 'No customer turns.',
                'ai_resolved':bool(ts) and ts[-1].data['decision']=='RESPOND' and not c.data.get('ever_escalated') and final_state=='COMPLETED'}
        db.add(CallEvent(call_id=cid,event_type='state',data={'state':final_state}));db.commit();snapshot=serialize(c)
    await publish({'type':'state','call_id':cid,'data':snapshot})

async def end(cid:str,provider_ended:bool=False,failed:bool=False,reason:str|None=None)->dict:
    async with locks.setdefault(cid,asyncio.Lock()):
        current=detail(cid)
        if current['state'] in TERMINAL:return current
        if not provider_ended:
            with SessionLocal() as db:pid=get_call(db,cid).provider_call_id
            try:await provider(current['mode']).end_call(pid or cid)
            except Exception:
                await event(cid,'end_error',{'message':'Provider could not confirm hangup.'})
                raise HTTPException(503,'Provider could not confirm hangup; retry or use the provider console')
        await _finish(cid,'FAILED' if failed else 'COMPLETED',reason or ('fatal_failure' if failed else 'provider_hangup' if provider_ended else 'manual_end'))
        return detail(cid)

async def block_demo_card(cid:str)->dict:
    async with locks.setdefault(cid,asyncio.Lock()):
        c=detail(cid)
        if c['state'] in TERMINAL:raise HTTPException(409,'Call is no longer active')
        if c['authentication_status']!='VERIFIED':raise HTTPException(403,'Verify the synthetic customer first')
        result=core_banking.block_demo_card(c['customer_id'])
        await event(cid,'demo_card_block',result)
        return result

async def silence_check(cid:str,force_provider_timeout:bool=False)->dict|None:
    async with locks.setdefault(cid,asyncio.Lock()):
        current=detail(cid)
        if current['state'] not in {'WAITING','LISTENING','SPEAKING','ESCALATING'}:return None
        if current['state'] in {'SPEAKING','ESCALATING'} and not force_provider_timeout:return None
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(current['last_activity'])).total_seconds()
        stage=current.get('silence_stage',0)
        target=stage+1 if force_provider_timeout else (3 if elapsed>=settings.silence_end_seconds else 2 if elapsed>=settings.silence_second_seconds else 1 if elapsed>=settings.silence_first_seconds else 0)
        if target<=stage:return None
        target=min(target,3)
        text='Are you still there?' if target==1 else "I'm still here whenever you're ready."
        with SessionLocal() as db:
            c=get_call(db,cid);c.data={**c.data,'silence_stage':target};db.commit()
        await event(cid,'silence',{'text':text,'stage':target,'turn_count':current['turn_count']})
        return {'text':text,'stage':target,'final':False}

async def silence_watchdog():
    while True:
        await asyncio.sleep(2)
        for c in list_calls():
            if c['state'] in TERMINAL:continue
            try:
                if CallTerminationController.duration_reached(c,settings.max_call_duration_minutes):
                    await end(c['id'],reason='max_duration')
                elif c['mode']!='REAL_PHONE_CALL':await silence_check(c['id'])
            except Exception:pass
