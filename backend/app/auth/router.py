import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import AuthResponse, LoginRequest, RegisterRequest
from app.auth.service import create_access_token, hash_password, verify_password
from app.common.audit import audit_event
from app.common.rate_limit import rate_limit
from app.db.models import User
from app.db.session import get_db


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse)
async def register(
    request: Request,
    payload: RegisterRequest,
    _: None = Depends(rate_limit(limit=15, window_sec=60)),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
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
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        audit_event(request=request, event="auth.login", outcome="fail", email=str(payload.email), detail="invalid_credentials")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user_id=str(user.id))
    audit_event(request=request, event="auth.login", outcome="success", user_id=str(user.id), email=str(payload.email))
    return AuthResponse(access_token=token)

