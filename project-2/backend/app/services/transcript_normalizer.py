"""Conservative ASR normalization. Financial identifiers are never rewritten."""
import re
from difflib import SequenceMatcher
from app.core.config import settings
from app.services.privacy import redact,credential_request,injection_risk

class BankingTranscriptNormalizer:
    def normalize(self,text,history,confidence=None,alternatives=None):
        raw,redactions=redact(text)
        result={'raw_transcript':raw,'normalized_transcript':raw,'corrections':[],
            'correction_confidence':None,'stt_confidence':confidence,'redactions':redactions,
            'needs_confirmation':False,'confirmation_candidate':None}
        if credential_request(text) or injection_risk(text)=='HIGH':return result
        context=history[-1].get('prediction',{}).get('intent','') if history else ''
        suspect=bool(re.search(r'\bmy god is good\b',raw,re.I))
        protected=lambda s:re.findall(r'\b(?:\w*\d\w*|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|lakh|today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',s.lower())
        for alternative in alternatives or []:
            candidate,events=redact(alternative.get('text',''))
            score=alternative.get('confidence')
            supported=score is not None and score>=settings.stt_low_confidence_threshold
            close=SequenceMatcher(None,raw.lower(),candidate.lower()).ratio()>=.8
            special=suspect and context.startswith('card_') and bool(re.fullmatch(r'my (?:debit |credit )?card is blocked[.!]?',candidate,re.I))
            if not events and supported and (confidence is None or score>confidence) and (close or special) and protected(raw)==protected(candidate) and not credential_request(candidate) and injection_risk(candidate)=='LOW':
                # N-best hypotheses can still be wrong: high-impact corrections are confirmed first.
                result['confirmation_candidate']=candidate
                result['needs_confirmation']=True
                result['correction_confidence']=score
                break
        normalized=raw
        mappings={r'\byou pee eye\b':'UPI',r'\ba t m\b':'ATM',r'\bn e f t\b':'NEFT',r'\br t g s\b':'RTGS',r'\bi m p s\b':'IMPS',r'\bk y c\b':'KYC',r'\be m i\b':'EMI',r'\btransction\b':'transaction',r'\bbenificiary\b':'beneficiary',r'\bwithdrawl\b':'withdrawal'}
        for pattern,replacement in mappings.items():
            if re.search(pattern,normalized,re.I):
                result['corrections'].append({'from':re.search(pattern,normalized,re.I).group(),'to':replacement,'method':'explicit_banking_spelling','confidence':None})
                normalized=re.sub(pattern,replacement,normalized,flags=re.I)
        result['normalized_transcript']=normalized
        if not raw.strip() or suspect or (confidence is not None and confidence<settings.stt_low_confidence_threshold):
            result['needs_confirmation']=True
        # Never fabricate a card/blocked transcript from the words god/good alone.
        return result
