from uuid import uuid4
from fastapi import APIRouter,HTTPException
from sqlalchemy import select
from app.schemas.operations import ArticleInput,RetrievalInput,GapReview
from app.database.store import SessionLocal,KnowledgeDocument,AdminAudit,KnowledgeGap,now
from app.services.rag import documents,index_article,refresh_cache,retrieve
from app.services.privacy import injection_risk,redact,unsafe_claim
from app.services.intent import classify,BY_ID
router=APIRouter(prefix='/api')

def public(data:dict)->dict:return {k:v for k,v in data.items() if k not in {'embedding','chunks'}}|{'chunk_count':len(data.get('chunks',[]))}
def validated(body:ArticleInput)->dict:
    data=body.model_dump()
    if injection_risk(body.content+' '+body.title)=='HIGH' or unsafe_claim(body.content):raise HTTPException(422,'Article contains unsafe instructions or credential requests')
    if redact(body.content)[1]:raise HTTPException(422,'Use synthetic non-sensitive policy text; detected PII must be removed')
    unknown=set(body.supported_intents)-set(BY_ID)
    if unknown:raise HTTPException(422,'Unsupported intent identifiers')
    return {**data,'intent':','.join(body.supported_intents),'subcategory':'admin','last_reviewed':now()[:10],'authentication_required':False,'aliases':[],'updated_at':now(),'index_status':'PENDING','admin_created':True}

@router.get('/knowledge')
def list_articles(category:str|None=None,q:str|None=None,include_disabled:bool=True):
    rows=documents(include_disabled)
    return [public(d) for d in rows if (not category or d.get('category')==category) and (not q or q.lower() in (d['title']+' '+d['content']).lower())]
@router.post('/knowledge',status_code=201)
def add(body:ArticleInput):
    data={**validated(body),'id':'KB-ADMIN-'+str(uuid4())[:12],'filename':'admin-managed'}
    with SessionLocal() as db:
        db.add(KnowledgeDocument(id=data['id'],data=data));db.add(AdminAudit(action='knowledge_created',data={'id':data['id'],'approved':data['approved']}));db.commit()
    return public(data)
@router.post('/knowledge/reindex')
def reindex():
    with SessionLocal() as db:
        count=0
        for row in db.scalars(select(KnowledgeDocument)):
            if row.data.get('enabled') and row.data.get('approved') and not row.data.get('legacy'):
                row.data=index_article(row.data);count+=1
        db.add(AdminAudit(action='knowledge_reindex',data={'count':count}));db.commit()
    refresh_cache();return {'indexed':count}
@router.post('/knowledge/test-retrieval')
def test_retrieval(body:RetrievalInput):
    safe=redact(body.query)[0];prediction=classify(safe)
    return {'prediction':prediction,'results':retrieve(safe,prediction['intent'])}
@router.get('/knowledge/{aid}')
def get(aid:str):
    with SessionLocal() as db:
        row=db.get(KnowledgeDocument,aid)
        if not row:raise HTTPException(404,'Article not found')
        return public(row.data)
@router.put('/knowledge/{aid}')
def edit(aid:str,body:ArticleInput):
    data=validated(body)
    with SessionLocal() as db:
        row=db.get(KnowledgeDocument,aid)
        if not row:raise HTTPException(404,'Article not found')
        row.data={**row.data,**data,'id':aid};db.add(AdminAudit(action='knowledge_edited',data={'id':aid}));db.commit();result=public(row.data)
    refresh_cache();return result
@router.delete('/knowledge/{aid}')
def disable(aid:str):
    with SessionLocal() as db:
        row=db.get(KnowledgeDocument,aid)
        if not row:raise HTTPException(404,'Article not found')
        row.data={**row.data,'enabled':False,'updated_at':now()};db.add(AdminAudit(action='knowledge_disabled',data={'id':aid}));db.commit()
    refresh_cache();return {'id':aid,'enabled':False}
@router.get('/knowledge-gaps')
def gaps():
    with SessionLocal() as db:return [{'id':g.id,'frequency':g.frequency,'status':g.status,'created_at':g.created_at,'updated_at':g.updated_at,**g.data} for g in db.scalars(select(KnowledgeGap).order_by(KnowledgeGap.frequency.desc()))]
@router.patch('/knowledge-gaps/{gid}')
def review(gid:str,body:GapReview):
    with SessionLocal() as db:
        g=db.get(KnowledgeGap,gid)
        if not g:raise HTTPException(404,'Knowledge gap not found')
        g.status=body.status;g.updated_at=now();db.add(AdminAudit(action='gap_reviewed',data={'id':gid,'status':body.status}));db.commit()
    return {'status':body.status}
