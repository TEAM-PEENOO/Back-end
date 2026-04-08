from datetime import datetime, timedelta, timezone
import base64
import json
from urllib.parse import urlencode
from urllib.parse import parse_qsl, urlparse, urlunparse

import httpx
from jose import jwt
from passlib.context import CryptContext

from app.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, user_id: str, expires_minutes: int = 60 * 24 * 7) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def verify_google_id_token(id_token: str) -> dict[str, str]:
    if not settings.google_client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
    except httpx.HTTPError as exc:
        raise ValueError(f"Google tokeninfo request failed: {exc!s}")
    if resp.status_code != 200:
        raise ValueError("Invalid Google id_token")

    payload = resp.json()
    if payload.get("aud") != settings.google_client_id:
        raise ValueError("Google token audience mismatch")
    if payload.get("email_verified") not in {"true", True}:
        raise ValueError("Google email not verified")

    email = payload.get("email")
    sub = payload.get("sub")
    if not email or not sub:
        raise ValueError("Google token missing required claims")
    return {"email": email, "sub": sub}


def build_google_oauth_url(*, state: str, redirect_uri: str) -> str:
    if not settings.google_client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    q = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"


async def exchange_google_code_for_id_token(*, code: str, redirect_uri: str) -> str:
    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("Google OAuth credentials are not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise ValueError(f"Google token exchange request failed: {exc!s}")
    if resp.status_code != 200:
        raise ValueError(f"Failed to exchange authorization code: status={resp.status_code}")
    id_token = resp.json().get("id_token")
    if not id_token:
        raise ValueError("Google response missing id_token")
    return id_token


def encode_oauth_state(*, app_redirect_uri: str) -> str:
    payload = {"r": app_redirect_uri}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_oauth_state(state: str) -> str | None:
    try:
        padded = state + "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        payload = json.loads(raw.decode())
        redirect = payload.get("r")
        return redirect if isinstance(redirect, str) and redirect else None
    except Exception:
        return None


def append_token_to_redirect_url(*, redirect_uri: str, access_token: str) -> str:
    parsed = urlparse(redirect_uri)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["access_token"] = access_token
    query_items["token_type"] = "bearer"
    query = urlencode(query_items)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def append_error_to_redirect_url(*, redirect_uri: str, error: str) -> str:
    parsed = urlparse(redirect_uri)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["error"] = error
    query = urlencode(query_items)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))

