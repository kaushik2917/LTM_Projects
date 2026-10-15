"""Deterministic customer handoff and reason-specific responses."""
import re
HUMAN_REASON='CUSTOMER_REQUESTED_HUMAN_AGENT'

def human_requested(text):
    text=text.lower().replace("â€™", "'").strip()
    if re.search(r"\b(?:do not|don't|dont|no need to)\s+(?:transfer|connect)|\b(?:do not|don't|dont)\s+(?:want|need)\s+(?:a |an )?(?:human|agent|person)|\b(?:not|no)\s+(?:a |an )?(?:human|agent)",text):return False
    person=r"(?:human(?: agent)?|(?:support |human |bank )?agent|person|someone|customer (?:care|service)|executive|bank representative|support)"
    return bool(re.search(r"\b(?:speak|talk)(?:ing)?\s+(?:to|with)\s+(?:(?:a|an|the|your|real|live)\s+)*"+person+r"\b",text)
        or re.search(r"\b(?:connect|transfer|put|patch)\b[^.!?]{0,45}\b(?:to|with|through to)\s+(?:(?:a|an|the|your|real|live)\s+)*"+person+r"\b",text)
        or re.search(r"\b(?:want|need|get me)\s+(?:(?:a|an|the|your|real|live)\s+)*"+person+r"\b",text)
        or re.search(r"(?:don't|do not|dont) want to (?:talk|speak) to (?:the |a )?bot",text)
        or re.fullmatch(r"(?:please )?(?:human(?: agent)?|customer care|customer service|support agent|agent|transfer me|(?:can you )?transfer (?:this|the) call)(?: please)?[.!?]*",text))

def security_context(text):
    if re.search(r'\b(?:what is|how to (?:avoid|prevent|identify))\b',text,re.I) and not re.search(r'\b(?:my card|my account|unauthori[sz]ed transaction|stole|stolen|hacked)\b',text,re.I):return False
    return bool(re.search(r"\b(?:stolen|stole|unauthori[sz]ed|unrecogni[sz]ed|fraud|scam|hacked|phishing)\b|don't recogni[sz]e|someone.{0,20}(?:used|using).{0,20}card|lost.{0,20}card|card.{0,20}lost",text,re.I))

def escalation_reason(prediction):
    if prediction.get('customer_requested_human'):return HUMAN_REASON
    if prediction['intent']=='complaint':return 'COMPLAINT'
    if prediction['risk']=='HIGH':return 'HIGH_RISK_FRAUD' if prediction.get('genuine_security') else 'POLICY_REQUIRED'
    return 'SPECIALIST_REQUIRED'

def escalation_response(reason,security=False,transfer=False):
    intro={'LOW_CONFIDENCE':"I want to make sure you get the right help. ", 'TECHNICAL_FAILURE':"I'm having trouble completing this request. ", 'COMPLAINT':"I'm sorry you have had this experience. "}.get(reason,'')
    message="Of course. I'll connect you with a support agent." if transfer else "I've placed your request in the support queue. A support agent can continue from here."
    if security or reason=='HIGH_RISK_FRAUD':message+=" Until then, please do not share your PIN, OTP, password, or CVV. Use your bank's verified support channel for urgent protection."
    return intro+message
