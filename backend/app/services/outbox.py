"""Outbox transactionnelle : écriture, réservation atomique (SKIP LOCKED + lease), complétion, échec/retry.

Le backend est l'UNIQUE autorité sur les tentatives : n8n n'effectue aucun retry de lui-même, il rapporte
`complete` ou `fail` et c'est ici que se décident backoff, nombre max d'essais et dead-letter.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import EVENT_WORKFLOW, EventType, LeadStatus, OutboxStatus, RunStatus
from app.models import AutomationRun, CrmMapping, Lead, OutboxEvent
from app.services.common import audit
from app.services.lead_state import transition

TERMINAL_ERROR_MESSAGE_MAX = 500


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    db: Session,
    *,
    org_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    event_type: EventType,
    dedupe_key: str,
    payload: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
    is_demo: bool = False,
) -> OutboxEvent:
    """Insère l'événement dans la transaction courante ; un `dedupe_key` déjà présent est un no-op."""
    s = get_settings()
    stmt = (
        pg_insert(OutboxEvent)
        .values(
            id=uuid.uuid4(),
            organization_id=org_id,
            lead_id=lead_id,
            event_type=event_type.value,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id or uuid.uuid4(),
            payload=payload or {},
            max_attempts=s.outbox_max_attempts,
            is_demo=is_demo,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    db.execute(stmt)
    return db.execute(select(OutboxEvent).where(OutboxEvent.dedupe_key == dedupe_key)).scalar_one()


def backoff_seconds(attempt: int) -> int:
    s = get_settings()
    return min(s.outbox_backoff_max_seconds, s.outbox_backoff_base_seconds * (2 ** max(0, attempt - 1)))


@dataclass
class Claimed:
    event: OutboxEvent
    run: AutomationRun


def _dead_letter(db: Session, ev: OutboxEvent, code: str, message: str | None = None) -> None:
    ev.status = OutboxStatus.DEAD_LETTER.value
    ev.locked_until = None
    ev.locked_by = None
    ev.last_error_code = code
    ev.last_error_at = _now()
    audit(db, org_id=ev.organization_id, lead_id=ev.lead_id, action="automation.dead_letter",
          correlation_id=ev.correlation_id, is_demo=ev.is_demo,
          metadata={"event_id": str(ev.id), "event_type": ev.event_type, "error_code": code,
                    "attempts": ev.attempt_count, "message": (message or "")[:TERMINAL_ERROR_MESSAGE_MAX]})
    if ev.event_type == EventType.LEAD_SUBMITTED.value and ev.lead_id:
        lead = db.get(Lead, ev.lead_id)
        if lead and lead.status not in (LeadStatus.ARCHIVED.value,):
            transition(db, lead, LeadStatus.FAILED, reason=code, strict=False)
    if ev.event_type == EventType.CRM_SYNC_REQUESTED.value and ev.lead_id:
        # La synchronisation CRM est abandonnée : le mapping doit refléter l'état définitif (pas "RETRYING").
        lead = db.get(Lead, ev.lead_id)
        if lead:
            db.execute(
                update(CrmMapping)
                .where(CrmMapping.organization_id == lead.organization_id, CrmMapping.contact_id == lead.contact_id,
                       CrmMapping.sync_status != "SYNCED")
                .values(sync_status="FAILED", last_error_code=code[:64])
            )


def _close_stale_run(db: Session, ev: OutboxEvent) -> None:
    """Lease expirée : la tentative précédente n'a jamais rapporté de résultat."""
    run = db.execute(
        select(AutomationRun).where(
            AutomationRun.outbox_event_id == ev.id,
            AutomationRun.attempt_count == ev.attempt_count,
            AutomationRun.status == RunStatus.STARTED.value,
        )
    ).scalar_one_or_none()
    if run:
        run.status = RunStatus.FAILED.value
        run.error_code = "LEASE_EXPIRED"
        run.error_message = "Aucun résultat reçu avant l'expiration de la réservation"
        run.finished_at = _now()
        run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)


def claim(db: Session, *, limit: int, worker: str) -> list[Claimed]:
    """Réserve atomiquement jusqu'à `limit` événements prêts ou dont la lease a expiré (récupération sur crash)."""
    s = get_settings()
    now = _now()
    limit = max(1, min(limit, s.outbox_claim_batch_max))
    due = or_(
        and_(
            OutboxEvent.status.in_([OutboxStatus.PENDING.value, OutboxStatus.RETRYING.value]),
            OutboxEvent.next_attempt_at <= now,
        ),
        and_(OutboxEvent.status == OutboxStatus.PROCESSING.value, OutboxEvent.locked_until < now),
    )
    rows = db.execute(
        select(OutboxEvent)
        .where(due)
        .order_by(OutboxEvent.next_attempt_at, OutboxEvent.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    claimed: list[Claimed] = []
    for ev in rows:
        if ev.status == OutboxStatus.PROCESSING.value:
            _close_stale_run(db, ev)
            if ev.attempt_count >= ev.max_attempts:
                _dead_letter(db, ev, "LEASE_EXPIRED", "Nombre maximal de tentatives atteint après expiration de lease")
                continue
        ev.attempt_count += 1
        ev.status = OutboxStatus.PROCESSING.value
        ev.locked_by = worker[:64]
        ev.locked_until = now + timedelta(seconds=s.outbox_lease_seconds)
        run = AutomationRun(
            lead_id=ev.lead_id,
            outbox_event_id=ev.id,
            correlation_id=ev.correlation_id,
            workflow_name=EVENT_WORKFLOW.get(EventType(ev.event_type), ev.event_type),
            event_type=ev.event_type,
            status=RunStatus.STARTED.value,
            attempt_count=ev.attempt_count,
            started_at=now,
            is_demo=ev.is_demo,
        )
        db.add(run)
        if ev.event_type == EventType.LEAD_SUBMITTED.value and ev.lead_id:
            lead = db.get(Lead, ev.lead_id)
            if lead:
                transition(db, lead, LeadStatus.PROCESSING, strict=False)
        claimed.append(Claimed(ev, run))
    db.flush()
    return claimed


def _get_for_update(db: Session, event_id: uuid.UUID) -> OutboxEvent | None:
    return db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()).scalar_one_or_none()


def _run_for(db: Session, ev: OutboxEvent) -> AutomationRun | None:
    return db.execute(
        select(AutomationRun).where(
            AutomationRun.outbox_event_id == ev.id, AutomationRun.attempt_count == ev.attempt_count
        )
    ).scalar_one_or_none()


def _finish_run(run: AutomationRun | None, status: RunStatus, *, error_code: str | None = None,
                error_message: str | None = None, details: dict | None = None) -> None:
    if run is None:
        return
    now = _now()
    run.status = status.value
    run.error_code = error_code
    run.error_message = (error_message or None) and error_message[:TERMINAL_ERROR_MESSAGE_MAX]
    run.finished_at = now
    run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
    if details:
        run.details = {**(run.details or {}), **details}


def complete(db: Session, *, event_id: uuid.UUID, attempt: int, outcome: str = "SUCCEEDED",
             details: dict | None = None) -> tuple[bool, str]:
    """Marque l'événement livré. Idempotent : un rejeu ou une tentative périmée est sans effet."""
    ev = _get_for_update(db, event_id)
    if ev is None:
        return False, "not_found"
    if ev.status == OutboxStatus.DELIVERED.value:
        return False, "already_delivered"
    if ev.status != OutboxStatus.PROCESSING.value or ev.attempt_count != attempt:
        return False, "stale_attempt"
    ev.status = OutboxStatus.DELIVERED.value
    ev.delivered_at = _now()
    ev.locked_until = None
    ev.locked_by = None
    ev.last_error_code = None
    status = RunStatus.MANUAL_REVIEW if outcome == "MANUAL_REVIEW" else RunStatus.SUCCEEDED
    _finish_run(_run_for(db, ev), status, details=details)
    return True, "applied"


def fail(db: Session, *, event_id: uuid.UUID, attempt: int, error_code: str, retryable: bool,
         message: str | None = None, retry_after_seconds: int | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Enregistre un échec : RETRYING (avec backoff exponentiel + jitter) ou DEAD_LETTER."""
    ev = _get_for_update(db, event_id)
    if ev is None:
        return False, "not_found", {}
    if ev.status != OutboxStatus.PROCESSING.value or ev.attempt_count != attempt:
        return False, "stale_attempt", {"status": ev.status}
    run = _run_for(db, ev)
    ev.last_error_code = error_code[:64]
    ev.last_error_at = _now()
    if retryable and ev.attempt_count < ev.max_attempts:
        delay = max(backoff_seconds(ev.attempt_count), retry_after_seconds or 0)
        delay = int(delay * (1 + random.random() * 0.2))  # noqa: S311 - jitter
        ev.status = OutboxStatus.RETRYING.value
        ev.next_attempt_at = _now() + timedelta(seconds=delay)
        ev.locked_until = None
        ev.locked_by = None
        _finish_run(run, RunStatus.RETRYING, error_code=error_code, error_message=message,
                    details={"next_attempt_in_seconds": delay})
        return True, "retrying", {"status": ev.status, "next_attempt_in_seconds": delay,
                                  "next_attempt_at": ev.next_attempt_at.isoformat()}
    _dead_letter(db, ev, error_code, message)
    _finish_run(run, RunStatus.FAILED, error_code=error_code, error_message=message)
    return True, "dead_letter", {"status": ev.status}


def requeue(db: Session, ev: OutboxEvent, *, actor_ref: str) -> None:
    """Reprise manuelle d'un événement en dead-letter / retry : budget d'essais neuf.

    `attempt_count` n'est jamais remis à zéro (l'historique des runs reste unique par (événement, tentative))."""
    s = get_settings()
    ev.status = OutboxStatus.PENDING.value
    ev.max_attempts = ev.attempt_count + s.outbox_max_attempts
    ev.next_attempt_at = _now()
    ev.locked_until = None
    ev.locked_by = None
    audit(db, org_id=ev.organization_id, lead_id=ev.lead_id, action="automation.manual_retry",
          actor_type="user", actor_ref=actor_ref, correlation_id=ev.correlation_id, is_demo=ev.is_demo,
          metadata={"event_id": str(ev.id), "event_type": ev.event_type})
