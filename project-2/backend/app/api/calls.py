import asyncio
import json
from fastapi import APIRouter,HTTPException,WebSocket,WebSocketDisconnect,Request
from pydantic import ValidationError
from app.schemas.operations import CallCreate,CallMessage,DemoVerify,ClientState
from app.services import calls
from app.services.telephony import capabilities
from app.core.config import settings

router=APIRouter(prefix='/api')

def socket_authorized(ws:WebSocket)->bool:
    from app.core.auth import session_valid,COOKIE
    origin=ws.headers.get('origin')
    token=ws.headers.get('sec-websocket-protocol','').split(',')
    protected=bool(settings.admin_api_token) or settings.telephony_provider=='twilio' or settings.app_mode=='real_phone'
    return origin in settings.cors_origins.split(',') and (not protected or session_valid(ws.cookies.get(COOKIE,'')) or (bool(settings.admin_api_token) and settings.admin_api_token in [x.strip() for x in token]))

@router.get('/telephony/capabilities')
def phone_config():return capabilities()
@router.get('/calls')
def list_calls():return calls.list_calls()
@router.post('/calls',status_code=201)
async def create(body:CallCreate):
    if body.mode=='REAL_PHONE_CALL':raise HTTPException(409,'Real calls enter through a signed telephony incoming webhook; the dashboard cannot originate a real call')
    return await calls.create_call(body.mode,body.customer_id)
@router.get('/calls/{cid}')
def detail(cid:str):return calls.detail(cid)
@router.post('/calls/{cid}/turns')
async def turn(cid:str,body:CallMessage):return await calls.call_turn(cid,**body.model_dump())
@router.post('/calls/{cid}/verify')
async def verify(cid:str,body:DemoVerify):
    try:return await calls.verify_demo(cid,body.customer_id,body.answer)
    except ValueError:raise HTTPException(404,'Demo customer not found')
@router.post('/calls/{cid}/interrupt')
async def interrupt(cid:str):return await calls.interrupt(cid)
@router.post('/calls/{cid}/state')
async def client_state(cid:str,body:ClientState):
    async with calls.locks.setdefault(cid,asyncio.Lock()):
        current=calls.detail(cid)
        if current['mode']=='REAL_PHONE_CALL':raise HTTPException(409,'Real phone state is controlled by the media session')
        if current['state'] in calls.TERMINAL:raise HTTPException(409,'Call is no longer active')
        if body.turn_count is not None and body.turn_count!=current['turn_count']:
            return {'state':current['state'],'ignored':True}
        await calls.state(cid,body.state,touch=body.state=='LISTENING' and current['state'] not in {'LISTENING','WAITING'})
        return {'state':body.state}
@router.post('/calls/{cid}/transfer')
async def transfer(cid:str):
    current=calls.detail(cid)
    if not current.get('ever_escalated'):
        await calls.call_turn(cid,'Please connect me to a human agent.',request_id='operator-transfer-request')
    return await calls.transfer(cid)
@router.post('/calls/{cid}/end')
async def end(cid:str):return await calls.end(cid)
@router.post('/calls/{cid}/demo-block-card')
async def block(cid:str):return await calls.block_demo_card(cid)

@router.websocket('/live-calls')
async def live(ws:WebSocket):
    if not socket_authorized(ws):await ws.close(code=1008);return
    await ws.accept(subprotocol='callsense' if settings.admin_api_token else None)
    queue=asyncio.Queue(maxsize=100);calls.subscribers.add(queue)
    try:
        await ws.send_json({'type':'snapshot','data':calls.list_calls()})
        while True:
            try:await ws.send_json(await asyncio.wait_for(queue.get(),timeout=20))
            except asyncio.TimeoutError:await ws.send_json({'type':'heartbeat'})
    except (WebSocketDisconnect,RuntimeError):pass
    finally:calls.subscribers.discard(queue)

@router.websocket('/telephony/audio/{cid}')
async def mock_audio(ws:WebSocket,cid:str):
    # Browser transport carries STT results and playback controls, not raw audio.
    if not socket_authorized(ws):await ws.close(code=1008);return
    await ws.accept(subprotocol='callsense' if settings.admin_api_token else None)
    try:
        calls.detail(cid)
        while True:
            packet=await ws.receive()
            if packet.get('type')=='websocket.disconnect':break
            if packet.get('bytes') is not None:
                await ws.send_json({'type':'error','message':'Raw audio is not supported by the browser adapter. Send final transcript events or configure Twilio Gather.'});continue
            try:
                raw=packet.get('text','')
                if len(raw)>14000:raise ValueError('Oversized message')
                data=json.loads(raw)
                if data.get('type')=='interrupt':
                    await calls.interrupt(cid);await ws.send_json({'type':'cancel_audio'});continue
                if data.get('type') not in {'transcript','text'}:raise ValueError('Expected transcript event')
                body=CallMessage.model_validate({k:v for k,v in data.items() if k!='type'})
                await ws.send_json({'type':'status','stage':'TRANSCRIBING'})
                result=await calls.call_turn(cid,**body.model_dump())
                await ws.send_json({'type':'turn','data':result})
            except (ValidationError,ValueError):await ws.send_json({'type':'error','message':'Invalid transcript event'})
            except HTTPException as exc:await ws.send_json({'type':'error','message':exc.detail})
    except (WebSocketDisconnect,HTTPException):pass

@router.post('/calls/{cid}/audio-turn')
async def audio_turn(cid:str,request:Request,request_id:str|None=None):
    from app.services.stt import SpeechToTextService,STTUnavailable,read_wav
    current=calls.detail(cid)
    if current['state'] in calls.TERMINAL:raise HTTPException(409,'Call is no longer active')
    if current['mode']=='REAL_PHONE_CALL':raise HTTPException(409,'Phone audio uses its signed provider stream')
    if request_id and len(request_id)>80:raise HTTPException(422,'Invalid request identifier')
    if request.headers.get('content-type','').split(';')[0]!='audio/wav':raise HTTPException(415,'Expected PCM WAV')
    maximum=int((settings.voice_max_utterance_seconds+3)*32000+128)
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>maximum:raise HTTPException(413,'Audio is too long; please speak in shorter parts')
    try:pcm=read_wav(data)
    except ValueError as exc:raise HTTPException(422,str(exc))
    await calls.state(cid,'TRANSCRIBING',True)
    try:transcript=await SpeechToTextService().transcribe(pcm)
    except STTUnavailable:
        await calls.state(cid,'LISTENING',True)
        raise HTTPException(503,{'message':'Speech recognition is unavailable. Please repeat.','fallback':settings.stt_fallback_provider})
    transcript['empty_transcript']=not bool(transcript['text'].strip())
    return await calls.call_turn(cid,transcript['text'] or '[Unclear speech]','voice',
        transcript['transcription_latency_ms'],request_id=request_id,speech_metadata=transcript)
