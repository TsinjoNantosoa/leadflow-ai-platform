"""Utilitaires transverses : audit, hash de requête, verrou d'idempotence, normalisation."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import AuditEvent, IdempotencyRecord
from app.observability.logging import correlation_id_var


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()


def request_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def advisory_lock(db: Session, key: str) -> None:
    """Verrou applicatif jusqu'à la fin de la transaction : sérialise les requêtes de même clé."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


def current_correlation_uuid() -> uuid.UUID | None:
    value = correlation_id_var.get()
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


def audit(
    db: Session,
    *,
    org_id: uuid.UUID,
    action: str,
    lead_id: uuid.UUID | None = None,
    actor_type: str = "system",
    actor_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
    is_demo: bool = False,
) -> AuditEvent:
    ev = AuditEvent(
        organization_id=org_id,
        lead_id=lead_id,
        actor_type=actor_type,
        actor_ref=actor_ref,
        action=action,
        correlation_id=correlation_id or current_correlation_uuid(),
        event_metadata=metadata or {},
        is_demo=is_demo,
    )
    db.add(ev)
    return ev


def run_idempotent(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: Any,
    handler: Callable[[], tuple[int, dict[str, Any]]],
) -> tuple[int, dict[str, Any], bool]:
    """Exécute `handler` au plus une fois par (scope, key).

    Rejeu avec la même empreinte -> réponse mémorisée. Même clé, corps différent -> 409.
    L'enregistrement est écrit dans la même transaction que les effets du handler.
    """
    advisory_lock(db, f"idem:{scope}:{key}")
    h = request_hash(payload)
    rec = db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
    ).scalar_one_or_none()
    if rec is not None:
        if rec.request_hash != h:
            raise ApiError(409, "idempotency_key_reuse", "Idempotency-Key déjà utilisée avec un contenu différent")
        return rec.response_status, rec.response_body, True
    status, body = handler()
    db.add(IdempotencyRecord(scope=scope, key=key, request_hash=h, response_status=status, response_body=body))
    db.flush()
    return status, body, False
