"""Regression tests for a call lifetime independent of utterance boundaries."""
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from app.core.config import settings, Settings
from app.database.store import SessionLocal, CallSession
from app.services import calls
from app.services.termination import CallTerminationController


def age_idle(cid, seconds):
    with SessionLocal() as db:
        c=db.get(CallSession,cid)
        c.state='LISTENING'
        c.data={**c.data,'last_activity':(datetime.now(timezone.utc)-timedelta(seconds=seconds)).isoformat()}
        db.commit()


@pytest.mark.parametrize('mode',['MOCK_CALL_MODE','BROWSER_VOICE_DEMO','TEXT_TEST_MODE'])
def test_many_turns_and_long_silence_only_explicit_end_completes(client,mode):
    initial=client.post('/api/calls',json={'mode':mode}).json()
    cid=initial['id']
    questions=['What is UPI?','What is NEFT?',"My debit card isn't working.",'Online.','What documents are needed for KYC?']
    for i,q in enumerate(questions+['What is an FD?']*26):
        response=client.post(f'/api/calls/{cid}/turns',json={'text':q})
        assert response.status_code==200,response.text
        if i==3:assert response.json()['context_used']
        # Playback end returns to listening; arbitrary silence cannot finish the call.
        client.post(f'/api/calls/{cid}/state',json={'state':'LISTENING','turn_count':i+1})
        age_idle(cid,[5,10,4,20,30,91,181,3600][i%8])
        client.portal.call(calls.silence_check,cid)
        current=client.get(f'/api/calls/{cid}').json()
        assert current['id']==cid and current['conversation_id']==initial['conversation_id']
        assert current['ended_at'] is None and current['summary'] is None
        assert current['state'] not in calls.TERMINAL and len(current['turns'])==i+1
    final=client.post(f'/api/calls/{cid}/end').json()
    assert final['state']=='COMPLETED' and final['ended_at'] and final['summary']
    assert final['termination_reason']=='manual_end'
    assert client.post(f'/api/calls/{cid}/end').json()['ended_at']==final['ended_at']
    assert sum(c['id']==cid for c in client.get('/api/calls').json())==1
    assert sum(e.get('state')=='COMPLETED' for e in final['events'])==1


def test_stale_playback_state_and_silence_cannot_end_new_turn(client):
    cid=client.post('/api/calls',json={'mode':'MOCK_CALL_MODE'}).json()['id']
    age_idle(cid,10000)
    client.post(f'/api/calls/{cid}/turns',json={'text':'What is NEFT?'})
    stale=client.post(f'/api/calls/{cid}/state',json={'state':'WAITING','turn_count':0}).json()
    assert stale['ignored']
    assert client.portal.call(calls.silence_check,cid) is None
    client.post(f'/api/calls/{cid}/end')
    assert client.post(f'/api/calls/{cid}/state',json={'state':'LISTENING','turn_count':1}).status_code==409
    assert client.portal.call(calls.silence_check,cid) is None


def test_turn_failure_is_recoverable(client,monkeypatch):
    cid=client.post('/api/calls',json={'mode':'MOCK_CALL_MODE'}).json()['id']
    original=calls.process
    monkeypatch.setattr(calls,'process',AsyncMock(side_effect=RuntimeError('temporary failure')))
    assert client.post(f'/api/calls/{cid}/turns',json={'text':'What is NEFT?'}).status_code==503
    assert calls.detail(cid)['ended_at'] is None
    monkeypatch.setattr(calls,'process',original)
    assert client.post(f'/api/calls/{cid}/turns',json={'text':'What is NEFT?'}).status_code==200
    client.post(f'/api/calls/{cid}/end')


def test_termination_policy_and_legacy_configuration():
    for reason in ['silence','utterance_complete','tts_complete','recognition_onend']:
        with pytest.raises(ValueError):CallTerminationController.validate(reason)
    for action in ['end','transfer','continue','reprompt']:
        assert Settings(_env_file=None,silence_final_action=action).silence_final_action in {'continue','reprompt'}
    c={'created_at':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()}
    assert not CallTerminationController.duration_reached(c,0)
    assert CallTerminationController.duration_reached(c,10)


def test_gather_empty_turns_keep_call_active(client):
    async def exercise():
        c=await calls.create_call('MOCK_CALL_MODE')
        for _ in range(10):
            prompt=await calls.silence_check(c['id'],True)
            assert not prompt['final']
            assert calls.detail(c['id'])['ended_at'] is None
        await calls.end(c['id'])
    client.portal.call(exercise)


def test_media_watchdog_never_ends_quiet_call(client,monkeypatch):
    from app.services.media import MediaSession
    monkeypatch.setattr('app.services.media.audio_speech_provider',lambda:AsyncMock())
    async def exercise():
        c=await calls.create_call('MOCK_CALL_MODE')
        ws=AsyncMock();session=MediaSession(ws,c['id'],'test-stream')
        session.fallback=AsyncMock()
        session.last_activity-=3600
        task=asyncio.create_task(session.watchdog())
        await asyncio.sleep(.6)
        task.cancel()
        with suppress(asyncio.CancelledError):await task
        session.fallback.assert_awaited_once()
        ws.close.assert_not_awaited()
        assert calls.detail(c['id'])['ended_at'] is None
        await calls.end(c['id'])
    client.portal.call(exercise)

def test_explicit_duration_limit_is_independent_of_silence(client,monkeypatch):
    monkeypatch.setattr(settings,'max_call_duration_minutes',0.001)
    async def exercise():
        c=await calls.create_call('MOCK_CALL_MODE')
        task=asyncio.create_task(calls.silence_watchdog())
        await asyncio.sleep(2.3)
        task.cancel()
        with suppress(asyncio.CancelledError):await task
        final=calls.detail(c['id'])
        assert final['state']=='COMPLETED' and final['termination_reason']=='max_duration'
    client.portal.call(exercise)
