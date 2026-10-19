"""Dépendances FastAPI d'authentification : utilisateurs (cookie + CSRF) et service n8n (Bearer)."""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import Role
from app.core.errors import ApiError
from app.database.session import get_db
from app.models import User, UserSession
from app.security.sessions import load_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class AuthContext:
    user: User
    session: UserSession

    @property
    def org_id(self):
        return self.user.organization_id

    @property
    def actor_ref(self) -> str:
        return self.user.email_normalized


def _origin_allowed(request: Request) -> bool:
    """Défense en profondeur contre le CSRF : si Origin/Referer est présent, il doit être autorisé."""
    allowed = set(get_settings().allowed_origins)
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in allowed
    referer = request.headers.get("referer")
    if referer:
        p = urlparse(referer)
        return f"{p.scheme}://{p.netloc}" in allowed
    return True  # appels non-navigateur (curl, tests) : le jeton CSRF reste obligatoire


def current_auth(request: Request, db: Annotated[Session, Depends(get_db)]) -> AuthContext:
    settings = get_settings()
    row = load_session(db, request.cookies.get(settings.session_cookie_name))
    if row is None:
        raise ApiError(401, "not_authenticated", "Authentification requise")
    if request.method not in SAFE_METHODS:
        if not _origin_allowed(request):
            raise ApiError(403, "origin_not_allowed", "Origine non autorisée")
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, row.csrf_token):
            raise ApiError(403, "csrf_invalid", "Jeton CSRF manquant ou invalide")
    return AuthContext(user=row.user, session=row)


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def dep(auth: Annotated[AuthContext, Depends(current_auth)]) -> AuthContext:
        if auth.user.role not in allowed:
            raise ApiError(403, "forbidden", "Droits insuffisants")
        return auth

    return dep


any_user = require_roles(Role.ADMIN, Role.SALES)
admin_only = require_roles(Role.ADMIN)


# --- Service-to-service (n8n) -------------------------------------------------------------------
@dataclass
class ServiceContext:
    name: str
    correlation_id: str | None


def service_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_lf_timestamp: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> ServiceContext:
    """Bearer secret partagé + horodatage récent (anti-rejeu) ; toute mutation exige en plus Idempotency-Key."""
    settings = get_settings()
    expected = settings.api_service_token.get_secret_value()
    if not expected:
        # Fail-closed : sans secret configuré, aucun appel interne n'est accepté.
        raise ApiError(503, "internal_api_disabled", "API interne non configurée")
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise ApiError(401, "invalid_service_credentials", "Credentials de service invalides")
    if x_lf_timestamp is None:
        raise ApiError(401, "timestamp_required", "En-tête X-LF-Timestamp requis")
    try:
        ts = float(x_lf_timestamp) / 1000.0
    except ValueError as exc:
        raise ApiError(401, "timestamp_invalid", "X-LF-Timestamp invalide (epoch en millisecondes)") from exc
    if abs(time.time() - ts) > settings.internal_max_clock_skew_seconds:
        raise ApiError(401, "timestamp_stale", "Requête trop ancienne ou horloge désynchronisée")
    return ServiceContext(name="n8n", correlation_id=x_correlation_id)
