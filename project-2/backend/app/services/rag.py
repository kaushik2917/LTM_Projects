import hashlib
import json
import re
from threading import RLock
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import select
from app.database.store import KnowledgeDocument,SessionLocal,now,AdminAudit,KnowledgeGap
from app.services.catalog import seed_articles,topics
from app.services.embeddings import semantic_index,canonical
from app.services.privacy import injection_risk
from app.core.config import settings

_cache=[]
_search_cache=[]
_matrices=None
_lock=RLock()

def fingerprint():
    return hashlib.sha256(('lsa-v3'+json.dumps(topics(),sort_keys=True)).encode()).hexdigest()

def embed(text:str)->list[float]:
    return semantic_index().vector(text).tolist()

def chunk_text(text:str,max_chars:int=900)->list[str]:
    sentences=re.split(r'(?<=[.!?])\s+',text.strip())
    chunks=[]; current=''
    for sentence in sentences:
        if len(current)+len(sentence)>max_chars and current:
            chunks.append(current);current=''
        current=(current+' '+sentence).strip()
    if current:chunks.append(current)
    return chunks

def index_article(data:dict)->dict:
    chunks=chunk_text(data['content'])
    vectors=semantic_index().vectors([data['title']+' '+c for c in chunks])
    return {**data,'chunks':[{'id':data['id']+f'-{i+1:02}','content':c,'embedding':v.tolist()} for i,(c,v) in enumerate(zip(chunks,vectors))],
            'embedding':semantic_index().vector(data['title']+' '+data['content']).tolist(),'index_status':'INDEXED','indexed_at':now(),'embedding_model':settings.embedding_model,'index_fingerprint':fingerprint()}

def refresh_cache()->None:
    global _cache,_search_cache,_matrices
    with SessionLocal() as db:
        items=[r.data for r in db.scalars(select(KnowledgeDocument)) if r.data.get('enabled',True) and r.data.get('approved',True) and r.data.get('index_status')=='INDEXED']
    model=semantic_index()
    search_items=[{**d,'content':c['content'],'embedding':c['embedding'],'chunk_id':c['id']} for d in items for c in d.get('chunks',[])]
    texts=[canonical(d['title']+' '+d['content']+' '+' '.join(d.get('keywords',[]))) for d in search_items]
    doc_words=TfidfVectorizer(ngram_range=(1,2),stop_words='english',sublinear_tf=True)
    matrices=(doc_words.fit_transform(texts),model.chars.transform(texts),np.array([d['embedding'] for d in search_items]),doc_words) if search_items else None
    with _lock:_cache=items;_search_cache=search_items;_matrices=matrices

def index_documents()->None:
    # Insert seeds once. An admin edit/disable must survive future restarts.
    with SessionLocal() as db:
        for item in db.scalars(select(KnowledgeDocument)):
            if not item.data.get('seed_version') and not item.data.get('admin_created'):
                item.data={**item.data,'enabled':False,'legacy':True}
        for data in seed_articles():
            row=db.get(KnowledgeDocument,data['id'])
            if not row:
                db.add(KnowledgeDocument(id=data['id'],data=index_article({**data,'updated_at':now()})))
            elif not row.data.get('admin_created'):
                refreshed={**row.data,**data,'enabled':row.data.get('enabled',True),'approved':row.data.get('approved',True)}
                row.data=index_article(refreshed) if row.data.get('index_fingerprint')!=fingerprint() else refreshed
        for row in db.scalars(select(KnowledgeDocument)):
            if row.data.get('admin_created') and row.data.get('index_status')=='INDEXED' and row.data.get('index_fingerprint')!=fingerprint():
                row.data=index_article(row.data)
        db.commit()
    refresh_cache()

def documents(include_disabled:bool=False)->list[dict]:
    if include_disabled:
        with SessionLocal() as db:
            return [r.data for r in db.scalars(select(KnowledgeDocument)) if not r.data.get('legacy')]
    with _lock:return list(_cache)

def retrieve(query:str,intent:str|None=None)->list[dict]:
    model=semantic_index(); vector=model.vector(query)
    q_words=model.words.transform([canonical(query)])
    q_chars=model.chars.transform([canonical(query)])
    with _lock:docs=list(_search_cache);matrices=_matrices
    if not docs:return []
    word_matrix,char_matrix,vectors,doc_words=matrices
    q_words=doc_words.transform([canonical(query)])
    lexical=(q_words@word_matrix.T).toarray()[0]
    fuzzy=(q_chars@char_matrix.T).toarray()[0]
    semantic=np.clip(vectors@vector,0,1)
    results=[]
    asks_procedure=bool(re.search(r'how|procedure|steps|what should|what do|can i',query,re.I))
    asks_concept=bool(re.search(r'what is|what are|meaning|define|explain',query,re.I))
    asks_numeric=bool(re.search(r'\b(rate|fee|charge|limit|percent|cost)\b',query,re.I))
    for i,doc in enumerate(docs):
        if injection_risk(doc['content'])=='HIGH':continue
        matched=intent in doc.get('supported_intents',[])
        base=.45*float(semantic[i])+.4*float(lexical[i])+.15*float(fuzzy[i])
        score=min(1,base+(.18 if matched else 0)+(.18 if asks_procedure and doc['source_type']=='BANK_POLICY' else .18 if asks_concept and doc['source_type']=='GENERAL_BANKING_INFORMATION' else 0)+(.12 if asks_numeric and doc['category']=='product_configuration' and matched else 0))
        if base<.08:continue
        results.append({k:v for k,v in doc.items() if k not in {'embedding','chunks'}}|{'similarity':round(float(semantic[i]),4),'score':round(score,4),'intent_match':matched,'lexical_score':round(float(lexical[i]),4),'character_score':round(float(fuzzy[i]),4)})
    ranked=sorted(results,key=lambda x:x['score'],reverse=True)
    unique={}
    for row in ranked:
        unique.setdefault(row['id'],row)
    return list(unique.values())[:settings.rag_top_k]

def record_gap(result:dict)->None:
    if result['decision'] not in {'ABSTAIN','CLARIFY'} or result['injection_risk']=='HIGH' or result.get('security_query'):return
    if result.get('awaiting_slot'):return
    key=hashlib.sha256(result['query'].lower().encode()).hexdigest()[:24]
    with SessionLocal() as db:
        item=db.get(KnowledgeGap,key)
        data={'customer_query':result['query'],'predicted_intent':result['prediction']['intent'],'retrieved_results':[e['id'] for e in result['evidence']],
              'retrieval_score':result['evidence'][0]['score'] if result['evidence'] else 0,'decision':result['decision'],'reason':result['reason']}
        if item:item.frequency+=1;item.updated_at=now();item.data=data
        else:db.add(KnowledgeGap(id=key,data=data))
        db.commit()
