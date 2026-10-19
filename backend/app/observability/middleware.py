from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.logging import correlation_id_var

log = logging.getLogger("leadflow.http")


def _valid_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Corrélation + journal de requête (méthode, chemin, statut, durée ; jamais de corps) + en-têtes de sécurité."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = _valid_uuid(request.headers.get("x-correlation-id")) or str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        request.state.correlation_id = cid
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.info(
                "request",
                extra={"method": request.method, "path": request.url.path, "status": status, "duration_ms": duration_ms},
            )
            correlation_id_var.reset(token)

    # Les en-têtes sont ajoutés via un second passage pour garder dispatch lisible.


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        cid = getattr(request.state, "correlation_id", None)
        if cid:
            response.headers["X-Correlation-ID"] = cid
        return response
