from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.dashboard.router import router as dashboard_router
from app.exam.router import router as exam_router
from app.persona.router import router as persona_router
from app.placement.router import router as placement_router
from app.teaching.router import router as teaching_router


def create_app() -> FastAPI:
    app = FastAPI(title="My Jeja API", version="0.1.0")

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth_router, prefix="/api/v1")
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

