from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.v1 import auth, dashboard, internal, public
from app.core.config import get_settings
from app.core.errors import ApiError, install_error_handlers
from app.database.session import get_engine
from app.observability.logging import configure_logging
from app.observability.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

log = logging.getLogger("leadflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    log.info("startup", extra={"env": s.app_env, "llm_provider": s.llm_provider, "crm_provider": s.crm_provider})
    yield
    get_engine().dispose()


def create_app() -> FastAPI:
    s = get_settings()
    docs = s.app_env != "production"
    app = FastAPI(
        title="LeadFlow AI API",
        version="1.0.0",
        description="API du MVP LeadFlow AI : formulaire public, dashboard authentifié, endpoints internes n8n.",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    install_error_handlers(app)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _db_unavailable(_, exc):  # base indisponible / réveil de Neon : réponse 503 retryable
        log.error("database_error", extra={"error_type": type(exc).__name__})
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": {"code": "service_unavailable", "message": "Service temporairement indisponible",
                                       "details": {}}}, status_code=503, headers={"Retry-After": "5"})

    # Ordre : les middlewares ajoutés en dernier sont les plus externes.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID", "Idempotent-Replayed", "Retry-After"],
        max_age=600,
    )

    @app.get("/health", tags=["ops"], summary="Liveness (ne touche pas la base : sûr pendant un cold start)")
    def health():
        return {"status": "ok", "service": "leadflow-api", "version": app.version}

    @app.get("/api/v1/health", tags=["ops"], summary="Liveness joignable via le proxy /api (réveil de Render Free)")
    def api_health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"], summary="Readiness : vérifie la connexion PostgreSQL")
    def ready():
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            raise ApiError(503, "database_unavailable", "Base de données indisponible") from exc
        return {"status": "ready"}

    prefix = "/api/v1"
    app.include_router(public.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)
    app.include_router(internal.router, prefix=prefix)
    return app


app = create_app()
