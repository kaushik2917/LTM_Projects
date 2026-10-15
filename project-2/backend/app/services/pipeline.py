import re
from time import perf_counter
from app.services.privacy import redact,injection_risk,verify,credential_request
from app.services.handoff import human_requested,security_context,HUMAN_REASON
from app.services.intent import classify,entities
from app.services.rag import retrieve
from app.services.generation import generator,voice_response
from app.services.decision import DecisionEngine,trust_score
from app.services.core_banking import core_banking
from app.services.customer_response import customer_evidence,approved_customer_text
from app.services.transcript_normalizer import BankingTranscriptNormalizer

async def process(text:str,history:list[dict],source:str='text',stt_ms:float|None=None,customer_context:dict|None=None,on_stage=None,speech_metadata:dict|None=None)->dict:
    started=perf_counter()
    async def stage(name):
        if on_stage:await on_stage(name)
    if source=='voice' and (speech_metadata or {}).get('empty_transcript'):text=''
    speech=BankingTranscriptNormalizer().normalize(text,history,(speech_metadata or {}).get('confidence'),(speech_metadata or {}).get('alternatives')) if source=='voice' else None
    original_text=text
    if speech:
        text=speech['normalized_transcript']
        if history and history[-1].get('awaiting_slot')=='speech_confirmation' and re.fullmatch(r'(yes|correct|that is right|yes that is right)[.! ]*',text,re.I):
            candidate=history[-1].get('speech_metadata',{}).get('confirmation_candidate')
            if candidate:
                text=candidate;speech['normalized_transcript']=text;speech['needs_confirmation']=False
                speech['corrections'].append({'method':'customer_confirmed','from':speech['raw_transcript'],'to':text,'confidence':None})
    safe,redactions=redact(text.strip());injection=injection_risk(original_text);security_query=credential_request(original_text)
    if speech:redactions=sorted(set(redactions+speech['redactions']))
    stages={'stt_ms':stt_ms,'tts_ms':None,'speech_end_ms':None}
    await stage('UNDERSTANDING');tick=perf_counter();effective=safe;followup=False
    explicit_human=human_requested(safe)
    if history and not explicit_human:
        last=history[-1]
        topic_continuation=last.get('awaiting_slot') not in {None,'speech_confirmation'} and len(safe.split())<12
        reference=bool(re.search(r'\b(it|that|arrive|yes|no)\b',safe,re.I)) and len(safe.split())<14
        card_followup=last.get('prediction',{}).get('intent') in {'card_blocked','card_payment_issue'} and bool(re.search(r'debit|credit|everywhere|what should|replacement|what now|what about',safe,re.I))
        if topic_continuation or reference or card_followup:
            effective=last.get('effective_query',last['query'])+'; customer clarification: '+safe
            followup=True
    prediction=classify(effective)
    if explicit_human and history:
        prediction['genuine_security']=prediction.get('genuine_security',False) or any(h.get('prediction',{}).get('genuine_security',False) for h in history)
        prediction['risk']='HIGH' if prediction['genuine_security'] else 'LOW'
    extracted=entities('; '.join([h['query'] for h in history]+[safe]) if explicit_human else effective)
    if followup and history[-1].get('awaiting_slot')=='payment_channel' and extracted['payment_channel']:
        prediction={**prediction,'intent':history[-1]['prediction']['intent'],'ambiguous':False,'description':history[-1]['prediction']['description']}
    if security_query or injection=='HIGH':prediction['risk']='HIGH'
    prediction['security_query']=security_query
    awaiting=None
    if prediction['ambiguous']:
        awaiting='payment_channel' if prediction['intent']=='transaction_status' else 'card_channel'
    if prediction['intent']=='card_blocked':
        if not re.search(r'\b(debit|credit|atm card)\b',effective,re.I):awaiting='card_type'
        elif not re.search(r'\b(atm|online|store|shop|everywhere)\b',effective,re.I):awaiting='card_channel'
    if speech and speech['needs_confirmation'] and not explicit_human and not security_query and injection!='HIGH':
        candidate=speech['confirmation_candidate']
        prediction['speech_clarification']=('Did you say: '+candidate.rstrip('.?!')+'?') if candidate else "I'm sorry, I didn't catch that clearly. Could you repeat it?"
        awaiting='speech_confirmation'
    payment_issue=bool(re.search(r'\bupi\b',effective,re.I) and re.search(r"(?:receiver|recipient|beneficiary).{0,35}(?:not|hasn.t|didn.t).{0,15}receiv",effective,re.I))
    if payment_issue and prediction['risk']!='HIGH' and not re.search(r'\b(pending|failed|successful|success)\b',effective,re.I):
        awaiting='payment_status'
    if followup and history[-1].get('awaiting_slot')=='payment_status':
        prediction={**prediction,'intent':history[-1]['prediction']['intent'],'ambiguous':False}
        awaiting=None if re.search(r'\b(pending|failed|successful|success)\b',safe,re.I) else 'payment_status'
    prediction['awaiting_slot']=awaiting
    lower=safe.lower()
    prediction['action_request']=prediction['intent']=='fund_transfer' and bool(re.search(r'^(?:please\s+)?(?:transfer|send|pay)\b|\btransfer\s+(?:inr|rs|\d)',lower))
    if prediction['intent']=='transaction_status' and re.search(r'check my|show my|my transfer status',lower):prediction['authentication_required']=True
    verified=bool(customer_context and customer_context.get('authentication_status')=='VERIFIED' and customer_context.get('customer_id'))
    stages['intent_ms']=round((perf_counter()-tick)*1000,2)
    await stage('RETRIEVING');tick=perf_counter();evidence=retrieve(effective,prediction['intent'])
    if verified and prediction['authentication_required']:
        demo=core_banking.evidence(customer_context['customer_id'],prediction['intent'])
        if demo:evidence=[demo]+evidence[:4];awaiting=None;prediction['awaiting_slot']=None;prediction['ambiguous']=False
    operator_evidence=evidence
    evidence=customer_evidence(evidence)
    stages['retrieval_ms']=round((perf_counter()-tick)*1000,2)
    tick=perf_counter();proposed='';generation_error=None
    predecision,_,_=DecisionEngine().decide(safe,prediction,evidence,{'passed':True},injection,verified)
    if predecision=='RESPOND':
        await stage('GENERATING')
        try:proposed=await generator().generate(effective,evidence)
        except Exception:generation_error='Generation provider unavailable; no unverified answer released.'
    stages['generation_ms']=round((perf_counter()-tick)*1000,2)
    await stage('VERIFYING');tick=perf_counter();verification=verify(proposed,evidence)
    decision,reason,policy=DecisionEngine().decide(safe,prediction,evidence,verification,injection,verified)
    answer=approved_customer_text(policy or proposed)
    score=trust_score(prediction,evidence[0]['score'] if evidence else 0,verification['grounding'],bool(evidence),.7 if awaiting else 1,injection)
    answer_type={'CLARIFY':'CLARIFICATION','VERIFY':'SECURITY_GUIDANCE','ESCALATE':'ESCALATION','ABSTAIN':'SECURITY_GUIDANCE' if security_query or injection=='HIGH' else 'ABSTENTION'}.get(decision,evidence[0]['source_type'] if evidence else 'ABSTENTION')
    stages['verification_ms']=round((perf_counter()-tick)*1000,2);stages['total_ms']=round((perf_counter()-started)*1000,2)
    result={'query':safe,'effective_query':effective,'source':source,'answer':answer,'display_response':answer,'voice_response':voice_response(answer),'answer_type':answer_type,
            'prediction':prediction,'original_intent':history[-1]['prediction']['intent'] if followup else None,'context_used':followup,'context_certainty':.7 if awaiting else 1,'awaiting_slot':awaiting,
            'entities':extracted,'evidence':evidence,'verification':verification,'trust':score,'decision':decision,'reason':reason,'risk':prediction['risk'],
            'privacy':{'redacted':bool(redactions),'types':redactions},'injection_risk':injection,'security_query':security_query,'latency':stages,'generation_error':generation_error,
            'proposed_answer':redact(proposed)[0] if verification['passed'] else '[Withheld: unverified generation]','handoff':None}
    result['operator_metadata']={'synthetic_profile':bool(customer_context and customer_context.get('customer_id')),'adapter':'MockCoreBankingAdapter','evidence_sources':[{'id':e['id'],'content':e['content']} for e in operator_evidence]}
    if speech:
        result['raw_transcript']=speech['raw_transcript'];result['normalized_transcript']=speech['normalized_transcript']
        result['speech_metadata']={**{k:v for k,v in (speech_metadata or {}).items() if k not in {'text','alternatives'}},**speech}
    if decision=='ESCALATE':
        result['escalation_reason']=reason
        result['handoff']={'customer_summary':safe,'conversation_summary':' -> '.join([h['query'] for h in history[-6:]]+[safe]),'intent':prediction['intent'],'entities':extracted,
            'previous_messages':[{'customer':h['query'],'assistant':h['answer']} for h in history[-6:]],'risk':prediction['risk'],'confidence':prediction['confidence'],'trust_score':score['score'],
            'reason':reason,'escalation_reason':reason,'customer_requested_human':explicit_human,'handoff_mode':'queue',
            'previous_banking_issue':next((h['prediction']['intent'] for h in reversed(history) if h['prediction']['intent']!='human_agent_request'),None),
            'conversation_turns':len(history)+1,'authentication_status':(customer_context or {}).get('authentication_status','UNVERIFIED'),
            'escalation_reasons':[reason]+(['HIGH_RISK_FRAUD'] if explicit_human and prediction.get('genuine_security') else []),'supporting_signals':[prediction['description'],'No real account actions are executed'],'knowledge_articles':[e['id'] for e in evidence],
            'suggested_next_action':'Review the masked issue and direct the caller to a verified support channel.','information_required':['Issue timeline and non-sensitive problem description'],
            'steps_already_attempted':[h['answer'] for h in history[-3:]],'simulated':True,'priority':'URGENT' if prediction['risk']=='HIGH' else 'NORMAL'}
    return result
