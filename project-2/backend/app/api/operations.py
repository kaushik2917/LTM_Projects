from dataclasses import asdict
from collections import Counter
from statistics import mean
from fastapi import APIRouter,HTTPException
from sqlalchemy import select
from app.database.store import SessionLocal,CallSession,Turn,KnowledgeGap,AuthenticationEvent,AdminAudit,EvaluationRun
from app.schemas.operations import RetrievalInput
from app.services.core_banking import core_banking
from app.services.intent import INTENTS,classify
from app.services.privacy import redact
from app.services import calls
from app.services.rag import documents
from app.services.telephony import capabilities
from app.services.speech import SpeechService
from app.core.config import settings
router=APIRouter(prefix='/api')

@router.get('/config')
def configuration():
    return {'mock_mode':settings.mock_mode,'llm_provider':'mock' if settings.mock_mode else settings.llm_provider,'llm_model':settings.llm_model,
        'tts_enabled':settings.tts_enabled and settings.enable_tts,'rag_top_k':settings.rag_top_k,'embedding_model':settings.embedding_model,
        'speech':SpeechService().configuration(),'synthetic_only':True,'telephony':capabilities(),'intent_count':len(INTENTS),'knowledge_count':len(documents()),
        'admin_token_required':bool(settings.admin_api_token),'version':'2.0.0','call_states':calls.STATES}
@router.get('/intents')
def intent_library():return [asdict(i) for i in INTENTS]
@router.post('/intents/test')
def test_intent(body:RetrievalInput):return classify(redact(body.query)[0])
@router.get('/demo-customers')
def customers():return core_banking.list_customers()
@router.get('/demo-customers/{cid}')
def customer(cid:str):
    try:return core_banking.get_customer(cid)
    except ValueError:raise HTTPException(404,'Demo customer not found')
@router.get('/demo-customers/{cid}/{resource}')
def resource(cid:str,resource:str):
    profile=customer(cid)
    if resource not in {'accounts','transactions','cards','loans','deposits','transfers'}:raise HTTPException(404,'Resource not found')
    return {'synthetic':True,'customer_id':cid,'data':profile[resource]}
@router.get('/security-events')
def security_events():
    with SessionLocal() as db:
        turns=[{'id':t.id,'created_at':t.created_at,'call_id':t.data.get('call_id'),'query':t.data['query'],'decision':t.data['decision'],'risk':t.data['risk'],'privacy':t.data['privacy'],'injection_risk':t.data['injection_risk'],'reason':t.data['reason']} for t in db.scalars(select(Turn).order_by(Turn.created_at.desc())) if t.data['privacy']['redacted'] or t.data['injection_risk']=='HIGH' or t.data['risk']=='HIGH']
        auth=[{'id':a.id,'created_at':a.created_at,'call_id':a.call_id,'status':a.status,**a.data} for a in db.scalars(select(AuthenticationEvent).order_by(AuthenticationEvent.created_at.desc()))]
        audit=[{'id':a.id,'created_at':a.created_at,'action':a.action,**a.data} for a in db.scalars(select(AdminAudit).order_by(AdminAudit.created_at.desc()))]
        return {'interactions':turns,'authentication':auth,'admin_audit':audit}
@router.get('/operations/analytics')
def analytics():
    with SessionLocal() as db:
        items=[calls.serialize(c) for c in db.scalars(select(CallSession))]
        data=[t.data for t in db.scalars(select(Turn)) if t.data.get('call_id')]
        evaluation=db.scalar(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(1))
        gaps=[{'id':g.id,'frequency':g.frequency,'status':g.status,**g.data} for g in db.scalars(select(KnowledgeGap).order_by(KnowledgeGap.frequency.desc()).limit(10))]
    n=len(data) or 1
    return {'total_calls':len(items),'live_calls':sum(c['state'] not in calls.TERMINAL for c in items),'completed_calls':sum(c['state']=='COMPLETED' for c in items),
        'ai_resolved_calls':sum(c.get('ai_resolved',False) for c in items),'escalated_calls':sum(c.get('ever_escalated',False) for c in items),
        'average_duration_seconds':round(mean(c['duration_seconds'] for c in items),1) if items else 0,'average_latency_ms':round(mean(t['latency']['total_ms'] for t in data),1) if data else 0,
        'average_turns':round(len(data)/len(items),2) if items else 0,'clarification_rate':sum(t['decision']=='CLARIFY' for t in data)/n,'abstention_rate':sum(t['decision']=='ABSTAIN' for t in data)/n,
        'retrieval_success':sum(bool(t['evidence']) and t['evidence'][0]['score']>=.24 for t in data)/n,'decision_distribution':dict(Counter(t['decision'] for t in data)),
        'risk_distribution':dict(Counter(t['risk'] for t in data)),'intent_distribution':dict(Counter(t['prediction']['intent'] for t in data)),
        'trust_distribution':dict(Counter('80-100' if t['trust']['score']>=80 else '60-79' if t['trust']['score']>=60 else '40-59' if t['trust']['score']>=40 else '0-39' for t in data)),
        'latency_by_stage':{key:round(mean(v),2) if (v:=[t['latency'][key] for t in data if t['latency'].get(key) is not None]) else None for key in ['speech_end_ms','stt_ms','intent_ms','retrieval_ms','generation_ms','verification_ms','tts_ms']},
        'intent_accuracy':evaluation.data.get('metrics',{}).get('intent_accuracy') if evaluation else None,'knowledge_gaps':gaps,
        'high_risk_count':sum(t['risk']=='HIGH' for t in data),'pii_redactions':sum(t['privacy']['redacted'] for t in data),'injection_detections':sum(t['injection_risk']=='HIGH' for t in data)}
