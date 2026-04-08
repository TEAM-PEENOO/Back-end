import uuid
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    AuthResponse,
    GoogleAuthUrlResponse,
    GoogleCodeLoginRequest,
    GoogleLoginRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
)
from app.auth.service import (
    append_error_to_redirect_url,
    append_token_to_redirect_url,
    build_google_oauth_url,
    create_access_token,
    decode_oauth_state,
    encode_oauth_state,
    exchange_google_code_for_id_token,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user_id


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse)
async def register(
    request: Request,
    payload: RegisterRequest,
    _: None = Depends(rate_limit(limit=15, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    if settings.auth_google_only:
        raise HTTPException(status_code=403, detail="Email/password auth is disabled; use Google login")

    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        audit_event(request=request, event="auth.register", outcome="fail", email=str(payload.email), detail="email_exists")
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(id=uuid.uuid4(), email=str(payload.email), password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.register", outcome="success", user_id=str(user.id), email=str(payload.email))
    return AuthResponse(access_token=token)


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    _: None = Depends(rate_limit(limit=15, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    if settings.auth_google_only:
        raise HTTPException(status_code=403, detail="Email/password auth is disabled; use Google login")

    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        audit_event(request=request, event="auth.login", outcome="fail", email=str(payload.email), detail="invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.login", outcome="success", user_id=str(user.id), email=str(payload.email))
    return AuthResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        id=str(user.id),
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.post("/google", response_model=AuthResponse)
async def google_login(
    request: Request,
    payload: GoogleLoginRequest,
    _: None = Depends(rate_limit(limit=20, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    try:
        claims = await verify_google_id_token(payload.id_token)
    except ValueError as exc:
        audit_event(request=request, event="auth.google", outcome="fail", detail=str(exc))
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = claims["email"]
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        # Password is unused in google-only flow but column is required.
        user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(str(uuid.uuid4())))
        db.add(user)
        await db.commit()

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.google", outcome="success", user_id=str(user.id), email=email)
    return AuthResponse(access_token=token)


@router.get("/google")
@router.get("/google/login")
async def google_oauth_entry(
    redirecturi: str | None = Query(default=None, alias="redirecturi", description="Frontend app callback URI"),
    redirect_uri: str | None = Query(default=None, description="App/web redirect URI after backend issues JWT"),
):
    backend_callback = settings.google_oauth_redirect_uri
    if not backend_callback:
        raise HTTPException(status_code=500, detail="GOOGLE_OAUTH_REDIRECT_URI is not configured")
    app_redirect = redirecturi or redirect_uri or settings.google_app_redirect_default
    state = encode_oauth_state(app_redirect_uri=app_redirect)
    auth_url = build_google_oauth_url(state=state, redirect_uri=backend_callback)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    app_redirect_uri = decode_oauth_state(state) or settings.google_app_redirect_default
    try:
        id_token = await exchange_google_code_for_id_token(code=code, redirect_uri=settings.google_oauth_redirect_uri)
        claims = await verify_google_id_token(id_token)
    except ValueError as exc:
        audit_event(request=request, event="auth.google.callback", outcome="fail", detail=str(exc))
        fail_url = append_error_to_redirect_url(redirect_uri=app_redirect_uri, error="google_auth_failed")
        return RedirectResponse(url=fail_url, status_code=302)

    email = claims["email"]
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(str(uuid.uuid4())))
        db.add(user)
        await db.commit()

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.google.callback", outcome="success", user_id=str(user.id), email=email)
    success_url = append_token_to_redirect_url(redirect_uri=app_redirect_uri, access_token=token)
    return RedirectResponse(url=success_url, status_code=302)


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def google_auth_url() -> GoogleAuthUrlResponse:
    redirect_uri = settings.google_oauth_redirect_uri
    if not redirect_uri:
        raise HTTPException(status_code=500, detail="GOOGLE_OAUTH_REDIRECT_URI is not configured")
    state = secrets.token_urlsafe(24)
    try:
        auth_url = build_google_oauth_url(state=state, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return GoogleAuthUrlResponse(auth_url=auth_url, state=state)


@router.post("/google/code", response_model=AuthResponse)
async def google_code_login(
    request: Request,
    payload: GoogleCodeLoginRequest,
    _: None = Depends(rate_limit(limit=20, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    try:
        id_token = await exchange_google_code_for_id_token(code=payload.code, redirect_uri=payload.redirect_uri)
        claims = await verify_google_id_token(id_token)
    except ValueError as exc:
        audit_event(request=request, event="auth.google.code", outcome="fail", detail=str(exc))
        raise HTTPException(status_code=401, detail="Invalid Google code")

    email = claims["email"]
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(id=uuid.uuid4(), email=email, password_hash=hash_password(str(uuid.uuid4())))
        db.add(user)
        await db.commit()

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.google.code", outcome="success", user_id=str(user.id), email=email)
    return AuthResponse(access_token=token)

