from dataclasses import dataclass,asdict,field
import re
from app.services.handoff import human_requested,security_context
from app.services.catalog import topics,examples
from app.services.embeddings import semantic_index

@dataclass
class Intent:
    name: str
    description: str
    phrases: list[str]
    risk: str='LOW'
    authentication_required: bool=False
    allowed_action: str='Explain approved knowledge; account records require demo verification.'
    escalation_conditions: str='Active fraud, authority-required operation, or explicit human request.'
    category: str=''
    sample_utterances: list[str]=field(default_factory=list)

INTENTS=[Intent(t['id'],t['title'],t['aliases'],t['risk'],False,category=t['category'],sample_utterances=examples(t)) for t in topics()]
BY_ID={i.name:i for i in INTENTS}
ACCOUNT_INTENTS={'account_balance_information','transaction_history','card_status','loan_status','deposit_status','credit_dues','credit_limit','credit_billing','statement_download'}

def classify(text: str) -> dict:
    if human_requested(text):
        selected=BY_ID['human_agent_request']
        return {**asdict(selected),'intent':selected.name,'confidence':1.0,'second_best_intent':None,'second_best_confidence':0,
                'ambiguous':False,'authentication_required':False,'risk':'HIGH' if security_context(text) else 'LOW',
                'customer_requested_human':True,'genuine_security':security_context(text),'score_signals':['explicit human request'],
                'model':'Deterministic human handoff rule','candidates':[{'intent':selected.name,'score':1.0}]}
    ranked=semantic_index().intent_scores(text)
    name,confidence,signals=ranked[0]
    lower=text.lower().replace("\u2019","'")
    # Safety signal precedence is independent of semantic confidence.
    if re.search(r"\b(stolen|lost)\b.{0,20}\bcard\b|\bcard\b.{0,20}\b(stolen|lost)\b",lower):
        name='card_block'
    elif re.search(r"(don't|do not|not) recogni[sz]e|unauthori[sz]ed|unrecogni[sz]ed|unknown transaction|someone.{0,15}(?:used|using).{0,15}card",lower):
        name='unknown_transaction'
    elif re.search(r"\b(fraud|scam|hacked|phishing)\b",lower) and not re.search(r"what is|how to avoid|prevent|identify",lower):
        name=next((n for n,_,_ in ranked if BY_ID[n].risk=='HIGH'), 'fraud_report')
    elif re.search(r'\bcard\b.{0,20}\b(blocked|disabled)\b|\bblocked\b.{0,15}\bcard\b',lower) and not re.search(r'^(?:is|check|show)',lower):
        name='card_blocked'
    elif 'atm' in lower and re.search(r'no cash|cash.{0,15}(?:not|never|didn)|not.{0,15}cash',lower):
        name='ATM_CASH_NOT_RECEIVED'
    elif re.search(r"\bcard\b",lower) and re.search(r"not working|isn't working|payment failed|declined",lower):
        name='card_payment_issue'
    if name!=ranked[0][0]:
        chosen=next(r for r in ranked if r[0]==name)
        confidence,signals=chosen[1],chosen[2]
    selected=BY_ID[name]
    other=next(r for r in ranked if r[0]!=name)
    personal=bool(re.search(r"\b(my|our|latest|last five|last 5|check|show me|tell me my)\b",lower))
    auth=name in ACCOUNT_INTENTS and personal
    card_ambiguous=name=='card_payment_issue' and not re.search(r"\b(online|shop|store|pos|atm|everywhere)\b",lower)
    transfer_ambiguous=name=='transaction_status' and not re.search(r"\b(upi|imps|neft|rtgs)\b",lower)
    return {**asdict(selected),'intent':name,'confidence':round(confidence,4),'second_best_intent':other[0],
            'second_best_confidence':round(other[1],4),'ambiguous':card_ambiguous or transfer_ambiguous,
            'authentication_required':auth,'risk':'MEDIUM' if auth and selected.risk=='LOW' else selected.risk,
            'genuine_security':security_context(text),'score_signals':signals,'model':'TF-IDF + corpus-trained LSA + character similarity',
            'candidates':[{'intent':n,'score':round(s,4)} for n,s,_ in ranked[:5]]}

def entities(text: str) -> dict:
    amounts=re.findall(r'(?:\u20b9|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?',text,re.I)
    if not amounts:
        words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20}
        match=re.search(r'\b('+'|'.join(words)+r')[ -]+(hundred|thousand|lakh)[ -]+rupees?\b',text,re.I)
        if match:amounts=['INR '+str(words[match[1].lower()]*{'hundred':100,'thousand':1000,'lakh':100000}[match[2].lower()])]
        else:
            numeric=re.search(r'\b([\d,]+(?:\.\d{1,2})?)\s+rupees?\b',text,re.I)
            if numeric:amounts=['INR '+numeric[1]]
    channels=re.findall(r'\b(UPI|IMPS|NEFT|RTGS|ATM|POS|online|store|shop)\b',text,re.I)
    refs=re.findall(r'\b(?:reference|utr|ref)\s*[:#]?\s*([A-Z]{2,}[A-Z0-9-]{2,})\b',text,re.I)
    merchant=re.search(r'\b(?:merchant|at merchant)\s+([A-Za-z][A-Za-z ]{1,30})',text,re.I)
    return {'amounts':amounts,'amount':float(re.sub(r'[^\d.]','',amounts[-1])) if amounts else None,
            'currency':'INR' if amounts else None,'dates':re.findall(r'\b(?:today|yesterday|tomorrow|last week|next month)\b|\b\d{4}-\d{2}-\d{2}\b',text,re.I),
            'payment_channel':channels[-1].upper() if channels else None,
            'card_type':next((x for x in ['debit','credit'] if x+' card' in text.lower()),None),
            'account_type':next((x for x in ['savings','current','salary','joint','minor'] if x in text.lower()),None),
            'loan_type':next((x for x in ['personal','home','vehicle','education','gold','business'] if x+' loan' in text.lower()),None),
            'reference_numbers':refs,'merchant':merchant.group(1).strip() if merchant else None,
            'masked_identifiers':re.findall(r'\[(?:NUMBER|CREDENTIAL) REDACTED\]|\*{2,}\d{0,4}',text),
            'branch':next((x for x in ['central','riverside'] if x in text.lower()),None),
            'problem_type':next((x for x in ['failed','pending','duplicate','stolen','lost','refund'] if x in text.lower()),None)}

