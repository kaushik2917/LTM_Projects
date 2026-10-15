import asyncio
import pytest
from app.services.catalog import topics
from app.services.intent import classify
from app.services.pipeline import process
from app.services.handoff import human_requested,escalation_response,HUMAN_REASON
from app.services import calls
from app.database.store import SessionLocal,Escalation
from sqlalchemy import select

PHRASES=next(t['aliases'] for t in topics() if t['id']=='human_agent_request')
@pytest.mark.parametrize('query',PHRASES+["I'd rather speak to a human agent.","I'd like to speak to a person."])
def test_explicit_human_request(client,query):
    p=classify(query)
    assert p['intent']=='human_agent_request' and p['risk']=='LOW'
    r=asyncio.run(process(query,[]))
    assert r['decision']=='ESCALATE' and r['escalation_reason']==HUMAN_REASON
    assert r['handoff']['customer_requested_human']
    assert not any(x in r['voice_response'].lower() for x in ['suspicious','fraud','demo','fictional','mock','prototype'])
    assert 'support queue' in r['voice_response']

@pytest.mark.parametrize('query',['Transfer INR 5000 to my beneficiary','Transfer me 500 rupees',"Don't transfer me to a human",'I do not want an agent','What is NEFT?'])
def test_not_human_request(query):
    assert not human_requested(query)

@pytest.mark.parametrize('issue',["My UPI payment hasn't arrived.",'What is NEFT?','What is my balance?','My card is blocked.'])
def test_context_and_authentication_do_not_block_handoff(client,issue):
    first=asyncio.run(process(issue,[]))
    r=asyncio.run(process('Transfer the call to a human agent.',[first],source='voice',speech_metadata={'confidence':.4}))
    assert r['prediction']['intent']=='human_agent_request' and r['decision']=='ESCALATE'
    assert r['risk']=='LOW' and r['awaiting_slot'] is None
    assert r['handoff']['previous_banking_issue']==first['prediction']['intent']
    assert issue in r['handoff']['conversation_summary']
    assert r['handoff']['authentication_status']=='UNVERIFIED'

@pytest.mark.parametrize('query',['Someone made an unauthorized transaction. Transfer me to an agent.','Someone stole my card. Transfer me to a human.'])
def test_actual_fraud_plus_human(client,query):
    r=asyncio.run(process(query,[]))
    assert r['risk']=='HIGH' and r['decision']=='ESCALATE'
    assert r['handoff']['escalation_reasons']==[HUMAN_REASON,'HIGH_RISK_FRAUD']
    assert 'PIN, OTP' in r['voice_response']

def test_previous_fraud_and_immediate_privacy(client):
    first=asyncio.run(process('Someone used my card without my permission.',[]))
    r=asyncio.run(process('Human agent',[first]))
    assert r['risk']=='HIGH' and r['handoff']['previous_banking_issue']=='unknown_transaction'
    secret=asyncio.run(process('My PIN is 1234. Transfer me to an agent.',[]))
    assert secret['decision']=='ABSTAIN' and '1234' not in str(secret)

def test_queue_persisted_without_ending_or_verifying(client):
    cid=client.post('/api/calls',json={'mode':'BROWSER_VOICE_DEMO'}).json()['id']
    r=client.post(f'/api/calls/{cid}/turns',json={'text':'Transfer the call to a human agent.'}).json()
    assert r['handoff']['call_id']==cid and r['handoff']['authentication_status']=='UNVERIFIED'
    c=calls.detail(cid)
    assert c['state']=='ESCALATING' and c['ended_at'] is None
    with SessionLocal() as db:
        packet=db.scalar(select(Escalation).where(Escalation.turn_id==r['id'])).packet
        assert packet['escalation_reason']==HUMAN_REASON and packet['risk']=='LOW'
    client.post(f'/api/calls/{cid}/end')

def test_escalation_response_reason_is_not_risk():
    for reason in [HUMAN_REASON,'COMPLAINT','LOW_CONFIDENCE','TECHNICAL_FAILURE','POLICY_REQUIRED','SPECIALIST_REQUIRED']:
        assert 'PIN' not in escalation_response(reason)
    assert 'PIN' in escalation_response('HIGH_RISK_FRAUD')
    assert "I'll connect" in escalation_response(HUMAN_REASON,transfer=True)

def test_educational_security_context_does_not_invent_incident(client):
    first=asyncio.run(process('What is phishing?',[]))
    r=asyncio.run(process('Human agent',[first]))
    assert r['risk']=='LOW' and 'PIN' not in r['voice_response']
