"""Local corpus-trained latent semantic analysis + lexical/fuzzy channels.
No paid API or downloaded model. Similarities are not calibrated probabilities.
"""
import re
from functools import lru_cache
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from threadpoolctl import threadpool_limits
from app.services.catalog import topics,examples,seed_articles

def canonical(text: str) -> str:
    text = text.lower().replace("\u2019", "'")
    text=re.sub(r'\b(?:for a banking customer|i was wondering about|could you walk me through|please outline|could you explain|please tell me about|i need help with|need some info on|hi i am calling about)\b',' ',text)
    substitutions = {
        r"\b(?:deducted|debited|taken out)\b":"debited",
        r"\b(?:didn't|did not|hasn't|has not|never)\b":"not",
        r"\b(?:got|came|come)\b":"received",
        r"\b(?:stuck|delayed|waiting)\b":"pending",
        r"\b(?:receiver|recipient|payee)\b":"beneficiary",
        r"\b(?:expires|expiring|expired)\b":"expiry renewal",
        r"\b(?:forgotten|forgot)\b":"forgot reset",
        r"\b(?:instalment|installments|instalments)\b":"installment",
        r"\b(?:withdrawl|withdrwal)\b":"withdrawal",
        r"\b(?:transction|transation)\b":"transaction",
        r"\b(?:benificiary|beneficary)\b":"beneficiary",
        r"\b(?:reciever|reciver)\b":"beneficiary",
        r"\b(?:kyc)\b":"kyc identity documents",
        r"\b(?:fd)\b":"fixed deposit",
        r"\b(?:rd)\b":"recurring deposit",
    }
    for pattern,replacement in substitutions.items():
        text = re.sub(pattern,replacement,text)
    return text

class SemanticIndex:
    def __init__(self):
        self.utterances=[]; self.labels=[]
        for t in topics():
            for s in [t['title'],*t['aliases'],*examples(t)]:
                self.utterances.append(canonical(s)); self.labels.append(t['id'])
        corpus = self.utterances+[canonical(a['title']+' '+a['content']) for a in seed_articles()]
        self.words=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,stop_words='english')
        matrix=self.words.fit_transform(corpus)
        self.chars=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=2,sublinear_tf=True,max_features=18000)
        char_matrix=self.chars.fit_transform(corpus)
        self.svd=TruncatedSVD(n_components=min(128,matrix.shape[0]-1,matrix.shape[1]-1),random_state=42)
        with threadpool_limits(limits=1):
            latent=normalize(self.svd.fit_transform(matrix))
        n=len(self.utterances)
        self.train_words=matrix[:n]; self.train_chars=char_matrix[:n]; self.train_vectors=latent[:n]
        self.label_indices={t['id']:np.array([i for i,label in enumerate(self.labels) if label==t['id']]) for t in topics()}
    def vector(self,text: str) -> np.ndarray:
        return self.vectors([text])[0]
    def vectors(self,texts: list[str]) -> np.ndarray:
        with threadpool_limits(limits=1):
            return normalize(self.svd.transform(self.words.transform([canonical(t) for t in texts])))
    def intent_scores(self,text: str) -> list[tuple[str,float,dict]]:
        q=canonical(text)
        w=(self.words.transform([q])@self.train_words.T).toarray()[0]
        c=(self.chars.transform([q])@self.train_chars.T).toarray()[0]
        s=np.clip(self.train_vectors@self.vector(text),0,1)
        scores=.45*w+.35*s+.20*c
        result=[]
        for label,idx in self.label_indices.items():
            best=idx[int(np.argmax(scores[idx]))]
            result.append((label,float(scores[best]),{'word':round(float(w[best]),4),'semantic':round(float(s[best]),4),'character':round(float(c[best]),4)}))
        return sorted(result,key=lambda x:x[1],reverse=True)

@lru_cache(maxsize=1)
def semantic_index() -> SemanticIndex:
    return SemanticIndex()

