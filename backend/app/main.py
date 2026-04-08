from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):
        # Keep server internals hidden from clients.
        req_id = getattr(request.state, "request_id", None)
        content = {"detail": "Internal server error"}
        if req_id:
            content["request_id"] = req_id
        return JSONResponse(status_code=500, content=content)

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

