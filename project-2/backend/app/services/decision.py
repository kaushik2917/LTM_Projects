import re
from app.services.handoff import escalation_reason,escalation_response
from app.services.privacy import credential_request

class DecisionEngine:
    def decide(self,query:str,prediction:dict,evidence:list[dict],verification:dict,injection:str,verified:bool=False)->tuple[str,str,str|None]:
        if injection=='HIGH':
            return 'ABSTAIN','Instruction override or internal-secret request detected.','I cannot reveal internal instructions or bypass banking policies. Please ask a banking support question.'
        if credential_request(query) or prediction.get('security_query'):
            return 'ABSTAIN','A secret was offered or requested; never collect or disclose it.','For your security, please do not share OTPs, PINs, passwords or CVV codes with anyone, including this assistant. Existing PINs and passwords cannot be retrieved or read back; use the secure reset option in your trusted banking app.'
        if prediction.get('customer_requested_human'):
            reason=escalation_reason(prediction)
            return 'ESCALATE',reason,escalation_response(reason,prediction.get('genuine_security',False))
        if re.search(r'\b(weather|sports score|recipe|bitcoin price|stock price|gold price|price of gold|election result)\b',query,re.I):
            return 'ABSTAIN','The requested live or non-banking information is outside the approved knowledge domain.','I can help with banking services and concepts, but I do not have verified information for that topic. I have recorded the knowledge gap for review.'
        if prediction.get('speech_clarification'):
            return 'CLARIFY','Speech recognition needs confirmation.',prediction['speech_clarification']
        if prediction.get('awaiting_slot')=='card_type':
            return 'CLARIFY','Card type needed for blocked-card guidance.',"I'm sorry you are having trouble with your card. Is this your debit card or credit card?"
        if prediction['risk']=='HIGH' or prediction['intent']=='complaint':
            reason=escalation_reason(prediction)
            return 'ESCALATE',reason,escalation_response(reason,prediction.get('genuine_security',False))
        if prediction['authentication_required'] and not verified:
            return 'VERIFY','Specific account records require a verified synthetic profile.','I can help with that. For account-specific information, I will need to verify your identity first. Please do not share your PIN, password or one-time codes.'
        if prediction.get('awaiting_slot')=='payment_channel':
            return 'CLARIFY','Payment channel is needed to choose the correct transfer procedure.','Which payment channel did you use: UPI, IMPS, NEFT or RTGS?'
        if prediction.get('awaiting_slot')=='payment_status':
            return 'CLARIFY','The reported UPI payment status is needed.','I can help with that. Does the payment currently show as pending, failed, or successful?'
        if prediction.get('awaiting_slot')=='card_channel' or prediction.get('ambiguous'):
            return 'CLARIFY','The card payment channel is unclear.','Was the payment attempted online, at a store, or at an ATM?'
        if prediction.get('action_request'):
            return 'VERIFY','A financial action requires an authenticated banking channel.',"I can explain the steps, but you will need to use your bank's secure channel to carry out the transaction."
        if not evidence or evidence[0]['score']<.24:
            if prediction['confidence']>=.22:
                return 'CLARIFY','Some banking context is present, but the question needs a clearer topic.','Could you tell me which banking product or issue you mean, and what you would like to know about it?'
            return 'ABSTAIN','No sufficiently relevant approved banking evidence was found.','I could not find reliable banking information for that question. I have flagged the knowledge gap for review; please describe the banking topic or ask for a support agent.'
        if not verification['passed']:
            return 'ABSTAIN','The proposed response failed independent evidence checks.','I want to make sure I give you the correct information. Please tell me more about what happened, or I can help you reach support.'
        return 'RESPOND','Relevant approved evidence supports the answer and safety checks passed.',None

def trust_score(prediction:dict,retrieval:float,grounding:float,has_evidence:bool,context:float=1,injection:str='LOW')->dict:
    components={'intent':round(25*prediction['confidence'],2),'retrieval':round(25*retrieval,2),'grounding':round(30*grounding,2),'context':round(20*context,2)}
    penalties={'ambiguity':10 if prediction.get('ambiguous') else 0,'risk':{'LOW':0,'MEDIUM':6,'HIGH':20}[prediction['risk']],'authentication':10 if prediction.get('authentication_required') else 0,'injection':40 if injection=='HIGH' else 0,'unsupported':10 if not has_evidence else 0}
    return {'score':round(max(0,min(100,sum(components.values())-sum(penalties.values())))),'components':components,'penalties':penalties,'formula':'25*intent + 25*retrieval + 30*grounding + 20*context - policy penalties','interpretation':'Measured similarity and verification factors; not a calibrated probability.'}
