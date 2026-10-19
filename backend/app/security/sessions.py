"""Sessions serveur : jeton opaque en cookie HttpOnly, hash en base, jeton CSRF (double soumission)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User, UserSession


def hash_token(token: str) -> str:
    # HMAC avec le secret serveur : un hash fuité ne permet pas de forger d'autres jetons.
    key = get_settings().session_secret.get_secret_value().encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, UserSession]:
    settings = get_settings()
    raw = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(row)
    db.flush()
    return raw, row


def load_session(db: Session, raw_token: str | None) -> UserSession | None:
    if not raw_token:
        return None
    row = db.execute(select(UserSession).where(UserSession.token_hash == hash_token(raw_token))).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at <= datetime.now(UTC):
        return None
    if not row.user.is_active:
        return None
    return row


def revoke_session(db: Session, row: UserSession) -> None:
    row.revoked_at = datetime.now(UTC)
