"""Expiring, signed HttpOnly operator sessions; no credentials in browser storage."""
import hashlib
import hmac
import secrets
import time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from app.core.config import settings

router = APIRouter(prefix='/api/auth')
COOKIE = 'callsense_session'


def session_valid(value: str) -> bool:
    if not settings.admin_api_token:
        return False
    try:
        expiry, nonce, signature = value.split('.')
        payload = f'{expiry}.{nonce}'
        expected = hmac.new(settings.admin_api_token.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return time.time() < int(expiry) <= time.time() + 28800 and hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def trusted_origin(origin: str | None) -> bool:
    return origin in settings.cors_origins.split(',')


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=512)


@router.post('/session')
def login(body: Login, request: Request, response: Response):
    if not trusted_origin(request.headers.get('origin')):
        raise HTTPException(403, 'Untrusted dashboard origin')
    if not settings.admin_api_token or not hmac.compare_digest(body.token, settings.admin_api_token):
        raise HTTPException(401, 'Invalid operations token')
    payload = f'{int(time.time()) + 28800}.{secrets.token_urlsafe(24)}'
    signature = hmac.new(settings.admin_api_token.encode(), payload.encode(), hashlib.sha256).hexdigest()
    response.set_cookie(COOKIE, f'{payload}.{signature}', httponly=True, samesite='strict',
                        secure=request.headers.get('origin', '').startswith('https://'), max_age=28800, path='/api')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True, 'expires_in_seconds': 28800}


@router.delete('/session')
def logout(request: Request, response: Response):
    if not trusted_origin(request.headers.get('origin')):
        raise HTTPException(403, 'Untrusted dashboard origin')
    response.delete_cookie(COOKIE, path='/api')
    return {'authenticated': False}
