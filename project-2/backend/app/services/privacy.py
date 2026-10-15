import re

def redact(text:str)->tuple[str,list[str]]:
    found=[]
    def secret(m):
        value=m.group(2)
        if value.lower().split()[0].strip('.,') in {'forgotten','incorrect','wrong','locked','blocked','expired','reset','not','missing'}:return m.group(0)
        found.append('credential')
        return '['+m.group(1).upper()+' REDACTED]'
    text=re.sub(r'\b(?:my\s+)?(pin|cvv|otp|password|passcode)\s*(?:is|:|=)\s*([^;\n]+)',secret,text,flags=re.I)
    text=re.sub(r'\b(pin|cvv|otp|password|passcode)\s+([\w@!#$%^&*.-]*\d[\w@!#$%^&*.-]*)',secret,text,flags=re.I)
    rules=[('email',r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'),('number',r'(?<!\w)\+?\d(?:[ -]?\d){5,18}(?!\w)')]
    for label,pattern in rules:
        def replacement(m):found.append(label);return '['+label.upper()+' REDACTED]'
        text=re.sub(pattern,replacement,text,flags=re.I)
    return text,sorted(set(found))

def injection_risk(text:str)->str:
    patterns=[r'ignore.{0,60}(?:instruction|polic|rule|previous)',r'(?:show|reveal|print|give).{0,40}(?:system|secret|prompt)',r'you are now',r'developer message',r'override.{0,30}(?:safety|policy)',r'<\|(?:system|im_start)',r'pretend.{0,30}(?:admin|unrestricted)',r'bypass.{0,30}(?:auth|security|verif)']
    return 'HIGH' if any(re.search(p,text,re.I) for p in patterns) else 'LOW'

def credential_request(text:str)->bool:
    # Reset/how-to questions are legitimate. Disclosure and secret submission are not.
    _,events=redact(text)
    if 'credential' in events:return True
    return bool(re.search(r'\b(?:tell|show|read|reveal|retrieve|give).{0,25}\b(?:my|your|the)\s+(?:upi\s+|card\s+|atm\s+)?(?:pin|cvv|otp|password)\b|\bwhat(?:\s+is|\x27s)\s+my\s+(?:upi\s+|card\s+)?(?:pin|cvv|otp|password)\b',text,re.I))

def unsafe_claim(answer:str)->bool:
    if re.search(r'\byour (?:card has been blocked|(?:money|funds) (?:has|have) been transferred|address has been changed|transaction has been reversed)\b',answer,re.I):return True
    for sentence in re.split(r'(?<=[.!?])\s+',answer):
        if re.search(r'\b(?:I have|successfully)\s+(?:blocked|transferred|paid)|\byour refund is guaranteed\b',sentence,re.I):return True
        if re.search(r'\b(?:share|tell|send|provide|enter|give).{0,25}\b(?:pin|otp|cvv|password)\b',sentence,re.I) and not re.search(r'\b(?:never|not|without|cannot|no need|stop)\b',sentence,re.I):return True
    return False

def verify(answer:str,evidence:list[dict])->dict:
    safe=[e for e in evidence if injection_risk(e['content'])=='LOW']
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',answer) if s.strip()]
    support=[any(s in e['content'] for e in safe) for s in sentences]
    supported=bool(support) and all(support)
    prohibited=unsafe_claim(answer)
    return {'passed':supported and not prohibited,'grounding':sum(support)/len(support) if support else 0,
            'checks':{'evidence_supported':supported,'no_prohibited_claims':not prohibited,'trusted_evidence':len(safe)==len(evidence)}}
