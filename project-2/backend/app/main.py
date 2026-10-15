import asyncio
from contextlib import asynccontextmanager,suppress
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.database.store import Base,engine
from app.services.rag import index_documents
from app.services.core_banking import seed_customers
from app.services.calls import silence_watchdog
from app.api.routes import router as legacy_router
from app.api.calls import router as calls_router
from app.api.knowledge import router as knowledge_router
from app.api.operations import router as operations_router
from app.api.telephony import router as telephony_router
from app.core.auth import router as auth_router,session_valid,trusted_origin,COOKIE

@asynccontextmanager
async def lifespan(app:FastAPI):
    if settings.app_mode=='real_phone' or settings.telephony_provider=='twilio':
        from app.services.telephony import capabilities
        config=capabilities()
        if not config['real_phone_configured']:
            import logging
            logging.getLogger(__name__).warning('Real phone mode not ready. Check TELEPHONY_PROVIDER and: %s', ', '.join(config['missing']))
    Base.metadata.create_all(engine)
    await asyncio.to_thread(index_documents)
    seed_customers()
    watchdog=asyncio.create_task(silence_watchdog())
    yield
    watchdog.cancel()
    with suppress(asyncio.CancelledError):await watchdog

app=FastAPI(title='Call Sense Bank Operations',version='2.0.0',description='Phone-first banking support with synthetic account services',lifespan=lifespan)
@app.middleware('http')
async def admin_boundary(request:Request,call_next):
    path=request.url.path
    public_hook=path in {'/api/telephony/incoming','/api/telephony/status'} or path.startswith('/api/telephony/turn/') or path.startswith('/api/telephony/dial-ended/')
    public_status=path in {'/api/health','/api/telephony/health','/api/telephony/capabilities','/api/auth/session'}
    needs_auth=bool(settings.admin_api_token) or settings.telephony_provider=='twilio' or settings.app_mode=='real_phone'
    if needs_auth and path.startswith('/api') and not public_status and not public_hook:
        import hmac
        header_ok=bool(settings.admin_api_token) and hmac.compare_digest(request.headers.get('x-admin-token',''),settings.admin_api_token)
        cookie_ok=session_valid(request.cookies.get(COOKIE,''))
        if cookie_ok and request.method not in {'GET','HEAD','OPTIONS'} and not trusted_origin(request.headers.get('origin')):
            return JSONResponse({'detail':'Untrusted dashboard origin'},status_code=403)
        if not header_ok and not cookie_ok:return JSONResponse({'detail':'Operations session required'},status_code=401)
    return await call_next(request)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(','),allow_methods=['GET','POST','PUT','DELETE','PATCH'],allow_headers=['Content-Type','X-Admin-Token'])
# Register extended endpoints first; preserve all remaining legacy paths.
app.include_router(operations_router)
app.include_router(knowledge_router)
app.include_router(calls_router)
app.include_router(telephony_router)
app.include_router(auth_router)
app.include_router(legacy_router)
