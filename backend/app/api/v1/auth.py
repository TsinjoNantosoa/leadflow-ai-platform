from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.database.session import get_db
from app.models import User
from app.schemas.dashboard import LoginIn, SessionOut, UserOut
from app.security.deps import AuthContext, _origin_allowed, any_user
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.sessions import create_session, revoke_session
from app.services.common import audit, normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, raw, max_age=s.session_ttl_hours * 3600, httponly=True, secure=s.cookie_secure,
        samesite=s.session_cookie_samesite, path="/",
    )


@router.post("/login", response_model=SessionOut, summary="Ouvrir une session")
def login(body: LoginIn, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    s = get_settings()
    if not _origin_allowed(request):
        raise ApiError(403, "origin_not_allowed", "Origine non autorisée")
    email = normalize_email(body.email)
    user = db.execute(select(User).where(User.email_normalized == email)).scalar_one_or_none()
    now = datetime.now(UTC)

    if user is not None and user.locked_until and user.locked_until > now:
        # Même message qu'un échec ordinaire : pas d'énumération de comptes.
        verify_password(body.password, None)
        raise ApiError(401, "invalid_credentials", "Identifiants invalides")

    ok = verify_password(body.password, user.password_hash if user and user.is_active else None)
    if not ok:
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= s.login_max_failures:
                user.locked_until = now + timedelta(minutes=s.login_lock_minutes)
                user.failed_login_count = 0
                audit(db, org_id=user.organization_id, action="auth.account_locked", actor_type="user",
                      actor_ref=user.email_normalized)
            db.commit()
        raise ApiError(401, "invalid_credentials", "Identifiants invalides")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    raw, row = create_session(db, user)
    audit(db, org_id=user.organization_id, action="auth.login", actor_type="user", actor_ref=user.email_normalized)
    db.commit()
    _set_cookie(response, raw)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=row.csrf_token)


@router.get("/me", response_model=SessionOut, summary="Session courante")
def me(auth: Annotated[AuthContext, Depends(any_user)]):
    return SessionOut(user=UserOut.model_validate(auth.user), csrf_token=auth.session.csrf_token)


@router.post("/logout", status_code=204, summary="Fermer la session")
def logout(response: Response, auth: Annotated[AuthContext, Depends(any_user)], db: Annotated[Session, Depends(get_db)]):
    revoke_session(db, auth.session)
    audit(db, org_id=auth.org_id, action="auth.logout", actor_type="user", actor_ref=auth.actor_ref)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = 204
    return response
