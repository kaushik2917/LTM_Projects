import json
from pathlib import Path
from statistics import mean
from app.services.pipeline import process

DATA_FILE=Path(__file__).resolve().parents[1]/'evaluation/queries.json'
def scenarios():
    return json.loads(DATA_FILE.read_text(encoding='utf-8-sig'))
def ratio(a,b):return round(a/b,4) if b else None
async def evaluate():
    import asyncio
    rows=[]
    for sample in scenarios():
        history=[];context={'customer_id':'CSB10001','authentication_status':'VERIFIED'} if sample.get('demo_verified') else None
        for query in sample.get('turns',[sample['query']]):
            result=await process(query,history,customer_context=context);history.append(result)
        expected=sample.get('expected_intent'); top2={result['prediction']['intent'],result['prediction']['second_best_intent']}
        relevant=sample.get('relevant_KB_document')
        rows.append({**sample,'actual_intent':result['prediction']['intent'],'actual_risk':result['risk'],'actual_decision':result['decision'],
          'intent_correct':expected==result['prediction']['intent'] if expected else None,'top2_correct':expected in top2 if expected else None,
          'decision_correct':sample['expected_decision']==result['decision'],'retrieval_correct':any(relevant in e['id'] for e in result['evidence']) if relevant else None,
          'grounded':result['verification']['passed'],'trust_score':result['trust']['score'],'latency_ms':sum(r['latency']['total_ms'] for r in history),
          'is_knowledge_gap':result['decision'] in {'ABSTAIN','CLARIFY'} and not result['security_query'] and result['injection_risk']=='LOW' and not result.get('awaiting_slot'),'turns_count':len(history),'pii_detected':result['privacy']['redacted'],'injection_detected':result['injection_risk']=='HIGH'})
        await asyncio.sleep(0)
    n=len(rows);labeled=[r for r in rows if r['expected_intent']];responses=[r for r in rows if r['actual_decision']=='RESPOND'];retrieval=[r for r in rows if r['retrieval_correct'] is not None]
    tp=sum(r['expected_decision']==r['actual_decision']=='ESCALATE' for r in rows)
    metrics={'intent_accuracy':ratio(sum(r['intent_correct'] for r in labeled),len(labeled)),
      'top2_intent_accuracy':ratio(sum(r['top2_correct'] for r in labeled),len(labeled)),
      'decision_accuracy':ratio(sum(r['decision_correct'] for r in rows),n),'risk_accuracy':ratio(sum(r['expected_risk']==r['actual_risk'] for r in rows),n),
      'escalation_precision':ratio(tp,sum(r['actual_decision']=='ESCALATE' for r in rows)),
      'escalation_recall':ratio(tp,sum(r['expected_decision']=='ESCALATE' for r in rows)),
      'correct_escalation_rate':ratio(tp,sum(r['expected_decision']=='ESCALATE' for r in rows)),
      'unnecessary_escalation_rate':ratio(sum(r['actual_decision']=='ESCALATE' and r['expected_decision']!='ESCALATE' for r in rows),sum(r['expected_decision']!='ESCALATE' for r in rows)),
      'unsafe_response_rate':ratio(sum(r['actual_decision']=='RESPOND' and (r['expected_decision']=='ABSTAIN' or r['expected_risk']=='HIGH' or not r['grounded']) for r in rows),n),
      'abstention_correctness':ratio(sum(r['expected_decision']==r['actual_decision']=='ABSTAIN' for r in rows),sum(r['actual_decision']=='ABSTAIN' for r in rows)),
      'retrieval_hit_rate':ratio(sum(r['retrieval_correct'] for r in retrieval),len(retrieval)),
      'retrieval_relevance':ratio(sum(r['retrieval_correct'] for r in retrieval),len(retrieval)),
      'grounding_success':ratio(sum(r['grounded'] for r in responses),len(responses)),
      'clarification_success':ratio(sum(r['decision_correct'] for r in rows if r['kind']=='multi_turn'),sum(r['kind']=='multi_turn' for r in rows)),
      'knowledge_gap_rate':ratio(sum(r['is_knowledge_gap'] for r in rows),n),
      'pii_detection':ratio(sum(r['pii_detected'] for r in rows if r.get('expected_pii')),sum(bool(r.get('expected_pii')) for r in rows)),
      'prompt_injection_detection':ratio(sum(r['injection_detected'] for r in rows if r.get('expected_injection')),sum(bool(r.get('expected_injection')) for r in rows)),
      'average_latency_ms':round(mean(r['latency_ms'] for r in rows),2),'average_trust_score':round(mean(r['trust_score'] for r in rows),1),'average_conversational_turns':round(mean(r['turns_count'] for r in rows),2)}
    subsets={k:{'count':len(v:=[r for r in rows if r['kind']==k]),'decision_accuracy':ratio(sum(r['decision_correct'] for r in v),len(v))} for k in sorted({r['kind'] for r in rows})}
    return {'metrics':metrics,'rows':rows,'sample_count':n,'subsets':subsets,'methodology':'Synthetic domain variations plus separately authored safety, misspelling, multi-turn and account-access checks. Wording templates overlap domain design; this is regression evidence, not an independent banking benchmark. Unsafe response is a rule-based proxy.'}

# Compatibility export for integrations that used the original tuple dataset.
DATASET=[(r['query'],r.get('expected_intent'),r['expected_risk'],r['expected_decision'],r.get('relevant_KB_document')) for r in scenarios()] if DATA_FILE.exists() else []
