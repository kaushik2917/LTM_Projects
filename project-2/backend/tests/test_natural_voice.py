import asyncio
import json
import re
from unittest.mock import AsyncMock
import numpy as np
import pytest
from app.core.config import settings
from app.services.audio import EndOfTurnDetector
from app.services.stt import SpeechToTextService,STTUnavailable,wav_bytes,read_wav
from app.services.transcript_normalizer import BankingTranscriptNormalizer
from app.services.pipeline import process
from app.services.intent import classify
from app.services import calls
from app.services.customer_response import FORBIDDEN

def test_natural_pause_preroll_and_postroll_are_one_utterance():
    detector=EndOfTurnDetector(1200,60,500,sample_rate=16000)
    quiet=bytes(640);voice=np.full(320,3000,dtype='<i2').tobytes()
    for frame in [quiet]*20+[voice]*30+[quiet]*35+[voice]*40:
        assert detector.feed(frame) is None
    for _ in range(59):assert detector.feed(quiet) is None
    result=detector.feed(quiet)
    assert result and detector.status=='UTTERANCE_COMPLETE'
    assert result.startswith(quiet*10) and result.endswith(quiet*15)
    assert len(result)>int(2*16000*2)
    assert not detector.buffer

def test_long_utterance_and_overflow_never_submit_truncated_audio():
    detector=EndOfTurnDetector(1200,60,500)
    frame=np.full(160,3000,dtype='<i2').tobytes()
    for _ in range(2000):assert detector.feed(frame) is None
    output=None
    for _ in range(60):output=detector.feed(bytes(320))
    assert output and len(output)>40*16000
    detector=EndOfTurnDetector(1200,2,500)
    for _ in range(150):assert detector.feed(frame) is None
    for _ in range(60):assert detector.feed(bytes(320)) is None
    assert detector.status=='UTTERANCE_TOO_LONG'

def test_normalizer_conservative_and_financial_values_preserved():
    n=BankingTranscriptNormalizer()
    history=[{'prediction':{'intent':'card_blocked'}}]
    raw=n.normalize('My god is good.',[],.4)
    assert raw['normalized_transcript']=='My god is good.' and raw['needs_confirmation']
    suggested=n.normalize('My god is good.',history,.4,[{'text':'My card is blocked.','confidence':.91}])
    assert suggested['needs_confirmation'] and suggested['confirmation_candidate']=='My card is blocked.'
    amount=n.normalize('Transfer 500 to REF123 today',history,.3,[{'text':'Transfer 5000 to REF124 tomorrow','confidence':.95}])
    assert amount['normalized_transcript']=='Transfer 500 to REF123 today' and not amount['confirmation_candidate']
    clean=n.normalize('You pee eye transction INR 500 yesterday',[],.9)
    assert clean['normalized_transcript']=='UPI transaction INR 500 yesterday'
    assert clean['corrections'] and clean['correction_confidence'] is None

@pytest.mark.parametrize('query',['My card is blocked.','My debit card got blocked.','My bank card is blocked.',
    'My card has been blocked.','My ATM card is blocked.','The bank blocked my card.','My card got disabled.'])
def test_blocked_card_vocabulary(query):
    assert classify(query)['intent']=='card_blocked'

def test_low_confidence_confirmation_and_secret_masking(client):
    cid=client.post('/api/calls',json={'mode':'BROWSER_VOICE_DEMO'}).json()['id']
    def turn(text,confidence=None,alternatives=[]):
        r=client.post(f'/api/calls/{cid}/turns',json={'text':text,'source':'voice','stt_confidence':confidence,'stt_alternatives':alternatives})
        assert r.status_code==200,r.text
        return r.json()
    first=turn('My card is blocked.',.3)
    assert first['decision']=='CLARIFY' and first['awaiting_slot']=='speech_confirmation'
    assert 'repeat' in first['voice_response']
    turn('My card is blocked.',.95)
    unclear=turn('My god is good.',.3,[{'text':'My card is blocked.','confidence':.91}])
    assert unclear['decision']=='CLARIFY' and 'Did you say' in unclear['voice_response']
    confirmed=turn('Yes.',.95)
    assert confirmed['normalized_transcript']=='My card is blocked.'
    secret=turn('My PIN is 1234.',.95)
    assert secret['decision']=='ABSTAIN'
    assert '1234' not in json.dumps(calls.detail(cid))
    assert secret['raw_transcript']==secret['normalized_transcript']
    assert calls.detail(cid)['ended_at'] is None
    client.post(f'/api/calls/{cid}/end')

@pytest.mark.parametrize('query',['My card has been blocked.','My debit card is blocked.','My card was stolen.',
    'What is my account balance?','What is NEFT?','I want to transfer INR 5000.','How can I reset my PIN?',
    'My PIN is 1234.','What are your fees?'])
def test_customer_language_policy(client,query):
    result=asyncio.run(process(query,[]))
    assert not FORBIDDEN.search(result['voice_response'])
    assert not FORBIDDEN.search(result['display_response'])
    assert not FORBIDDEN.search(result['answer'])

def test_verified_balance_and_card_context(client):
    context={'customer_id':'CSB10001','authentication_status':'VERIFIED'}
    r=asyncio.run(process('What is my account balance?',[],customer_context=context))
    assert r['decision']=='RESPOND' and r['verification']['passed'] and '24,850' in r['voice_response']
    assert not FORBIDDEN.search(r['voice_response']) and r['operator_metadata']['synthetic_profile']
    history=[]
    for question in ['My card is blocked.',"It's my debit card.",'It stopped working at the ATM.','What should I do now?','Can I request a replacement?']:
        r=asyncio.run(process(question,history));history.append(r)
        assert not FORBIDDEN.search(r['voice_response'])
    assert history[0]['awaiting_slot']=='card_type'
    assert history[1]['awaiting_slot']=='card_channel'
    assert all(r['context_used'] for r in history[1:])
    assert history[2]['decision']=='RESPOND'

def test_audio_endpoint_same_call_and_stt_fallback(client,monkeypatch):
    transcript={'text':'My card is blocked.','confidence':.95,'alternatives':[],'provider':'faster_whisper','transcription_latency_ms':14}
    mock=AsyncMock(return_value=transcript)
    monkeypatch.setattr(SpeechToTextService,'transcribe',mock)
    cid=client.post('/api/calls',json={'mode':'BROWSER_VOICE_DEMO'}).json()['id']
    wav=wav_bytes(np.full(16000,3000,dtype='<i2').tobytes())
    response=client.post(f'/api/calls/{cid}/audio-turn?request_id=audio-test',content=wav,headers={'Content-Type':'audio/wav'})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['raw_transcript']=='My card is blocked.' and result['call_id']==cid
    assert result['prediction']['intent']=='card_blocked'
    assert calls.detail(cid)['ended_at'] is None
    mock.side_effect=STTUnavailable()
    response=client.post(f'/api/calls/{cid}/audio-turn',content=wav,headers={'Content-Type':'audio/wav'})
    assert response.status_code==503 and response.json()['detail']['fallback']=='browser'
    assert calls.detail(cid)['ended_at'] is None
    assert client.post(f'/api/calls/{cid}/audio-turn',content=b'bad',headers={'Content-Type':'audio/wav'}).status_code==422
    assert read_wav(wav)==np.full(16000,3000,dtype='<i2').tobytes()
    client.post(f'/api/calls/{cid}/end')

def test_whisper_optional_and_explicit_azure_fallback(monkeypatch):
    from app.services import stt
    monkeypatch.setattr(settings,'stt_provider','faster_whisper')
    monkeypatch.setattr(settings,'stt_fallback_provider','browser')
    monkeypatch.setattr(stt._local,'transcribe',AsyncMock(side_effect=STTUnavailable()))
    with pytest.raises(STTUnavailable):asyncio.run(SpeechToTextService().transcribe(bytes(32000)))
    monkeypatch.setattr(settings,'stt_fallback_provider','azure')
    monkeypatch.setattr(stt.AzureSpeechProvider,'transcribe',AsyncMock(return_value={'text':'What is UPI?','confidence':.9}))
    assert asyncio.run(SpeechToTextService().transcribe(bytes(32000)))['fallback_used']

def test_no_false_financial_action_claims():
    from app.services.privacy import unsafe_claim
    for text in ['I have blocked your card.','Your money has been transferred.','Your address has been changed.','Your transaction has been reversed.']:
        assert unsafe_claim(text)
