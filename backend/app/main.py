import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse, Response, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
import sentry_sdk

from app.auth.router import router as auth_router
from app.common.security import RequestContextMiddleware, SecurityHeadersMiddleware
from app.config import settings
from app.dashboard.router import router as dashboard_router
from app.exam.router import router as exam_router
from app.persona.router import router as persona_router
from app.placement.router import router as placement_router
from app.subjects.router import router as subjects_router
from app.teaching.router import router as teaching_router


def create_app() -> FastAPI:
    app = FastAPI(title="My Jeja API", version="0.1.0")

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.app_env,
        )

    def _error_code_for_status(status_code: int) -> str:
        if status_code == 400:
            return "VALIDATION_ERROR"
        if status_code == 401:
            return "UNAUTHORIZED"
        if status_code == 403:
            return "FORBIDDEN"
        if status_code == 404:
            return "NOT_FOUND"
        if status_code == 409:
            return "CONFLICT"
        if status_code == 422:
            return "VALIDATION_ERROR"
        return "INTERNAL_ERROR"

    @app.middleware("http")
    async def wrap_success_response(request: Request, call_next):
        response = await call_next(request)
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.status_code == 204:
            return response
        if isinstance(response, (StreamingResponse, RedirectResponse)):
            return response
        ctype = response.headers.get("content-type", "")
        if "application/json" not in ctype:
            return response
        body = getattr(response, "body", None)
        if body is None:
            return response
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            return response
        if isinstance(parsed, dict) and ("data" in parsed or "error" in parsed):
            return response
        return JSONResponse(status_code=response.status_code, content={"data": parsed})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        req_id = getattr(request.state, "request_id", None)
        code = _error_code_for_status(exc.status_code)
        message = "Request failed"
        extra: dict = {}
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", code))
            message = str(exc.detail.get("message", message))
            extra = {k: v for k, v in exc.detail.items() if k not in {"code", "message"}}
        elif isinstance(exc.detail, str):
            message = exc.detail
        payload = {"error": {"code": code, "message": message}}
        if req_id:
            payload["error"]["request_id"] = req_id
        payload["error"].update(extra)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", None)
        payload = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        }
        if req_id:
            payload["error"]["request_id"] = req_id
        return JSONResponse(status_code=400, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Keep server internals hidden from clients.
        req_id = getattr(request.state, "request_id", None)
        payload = {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
        if req_id:
            payload["error"]["request_id"] = req_id
        return JSONResponse(status_code=500, content=payload)

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(subjects_router, prefix="/api/v1")
    app.include_router(persona_router, prefix="/api/v1")
    app.include_router(placement_router, prefix="/api/v1")
    app.include_router(teaching_router, prefix="/api/v1")
    app.include_router(exam_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

