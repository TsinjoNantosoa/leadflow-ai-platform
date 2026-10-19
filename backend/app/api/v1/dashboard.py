from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import EventType, LeadStatus, OutboxStatus
from app.core.errors import ApiError
from app.database.session import get_db
from app.models import AutomationRun, Lead, OutboxEvent
from app.schemas.dashboard import (
    AuditOut,
    FollowupDecision,
    FollowupOut,
    FollowupPatch,
    FollowupReviewItem,
    LeadDetail,
    LeadListItem,
    Page,
    RunOut,
)
from app.security.deps import AuthContext, admin_only, any_user
from app.services import followups as followup_svc
from app.services import outbox, views
from app.services.common import audit

router = APIRouter(tags=["dashboard"])
Db = Annotated[Session, Depends(get_db)]
Auth = Annotated[AuthContext, Depends(any_user)]
PageQ = Annotated[int, Query(ge=1, le=10_000)]
SizeQ = Annotated[int, Query(ge=1, le=100)]


@router.get("/leads", response_model=Page[LeadListItem], summary="Lister les leads")
def list_leads(
    db: Db, auth: Auth,
    status: Annotated[Literal["NEW", "PROCESSING", "QUALIFIED", "MANUAL_REVIEW", "READY", "FAILED", "ARCHIVED"] | None, Query()] = None,
    segment: Annotated[Literal["HOT", "WARM", "COLD"] | None, Query()] = None,
    service: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    review: bool | None = None,
    page: PageQ = 1,
    page_size: SizeQ = 20,
    sort: Literal["created_at", "score", "status", "name"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
):
    return views.list_leads(db, auth.org_id, status=status, segment=segment, service=service, q=q, review=review,
                            page=page, page_size=page_size, sort=sort, order=order)


@router.get("/leads/{lead_id}", response_model=LeadDetail, summary="Détail d'un lead")
def get_lead(lead_id: uuid.UUID, db: Db, auth: Auth):
    return views.lead_detail(db, auth.org_id, lead_id)


@router.post("/leads/{lead_id}/retry", status_code=202, summary="Relancer le traitement d'un lead")
def retry_lead(lead_id: uuid.UUID, db: Db, auth: Auth) -> dict[str, Any]:
    lead = db.execute(select(Lead).where(Lead.id == lead_id, Lead.organization_id == auth.org_id)
                      .with_for_update()).scalar_one_or_none()
    if lead is None:
        raise ApiError(404, "lead_not_found", "Lead introuvable")
    if lead.status == LeadStatus.ARCHIVED.value:
        raise ApiError(409, "lead_archived", "Un lead archivé ne peut pas être relancé")
    active = db.execute(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.lead_id == lead.id, OutboxEvent.event_type == EventType.LEAD_SUBMITTED.value,
            OutboxEvent.status.in_([OutboxStatus.PENDING.value, OutboxStatus.PROCESSING.value, OutboxStatus.RETRYING.value]),
        )
    ).scalar_one()
    if active:
        raise ApiError(409, "retry_already_pending", "Un traitement est déjà en cours ou planifié pour ce lead")
    n = db.execute(select(func.count()).select_from(OutboxEvent).where(
        OutboxEvent.lead_id == lead.id, OutboxEvent.event_type == EventType.LEAD_SUBMITTED.value)).scalar_one()
    ev = outbox.enqueue(db, org_id=lead.organization_id, lead_id=lead.id, event_type=EventType.LEAD_SUBMITTED,
                        dedupe_key=f"lead:{lead.id}:retry:{n}", payload={"reason": "manual_retry", "by": auth.actor_ref},
                        is_demo=lead.is_demo)
    audit(db, org_id=auth.org_id, lead_id=lead.id, action="lead.retry_requested", actor_type="user",
          actor_ref=auth.actor_ref, is_demo=lead.is_demo, correlation_id=ev.correlation_id,
          metadata={"event_id": str(ev.id), "from_status": lead.status})
    db.commit()
    return {"lead_id": str(lead.id), "event_id": str(ev.id), "status": "queued"}


@router.get("/metrics/overview", summary="Indicateurs agrégés (calculés depuis PostgreSQL)")
def metrics_overview(db: Db, auth: Auth, days: Annotated[int, Query(ge=3, le=90)] = 14) -> dict[str, Any]:
    return views.overview(db, auth.org_id, days)


@router.get("/automation-runs", response_model=Page[RunOut], summary="Historique des automatisations")
def automation_runs(
    db: Db, auth: Auth,
    lead_id: uuid.UUID | None = None,
    status: Literal["STARTED", "SUCCEEDED", "RETRYING", "FAILED", "MANUAL_REVIEW"] | None = None,
    workflow: Annotated[str | None, Query(max_length=64)] = None,
    page: PageQ = 1,
    page_size: SizeQ = 20,
):
    return views.list_runs(db, auth.org_id, lead_id=lead_id, status=status, workflow=workflow, page=page, page_size=page_size)


@router.post("/automation-runs/{run_id}/retry", status_code=202, summary="Reprise manuelle d'un événement (admin)")
def retry_run(run_id: uuid.UUID, db: Db, auth: Annotated[AuthContext, Depends(admin_only)]) -> dict[str, Any]:
    run = db.get(AutomationRun, run_id)
    ev = db.execute(select(OutboxEvent).where(OutboxEvent.id == run.outbox_event_id).with_for_update()
                    ).scalar_one_or_none() if run and run.outbox_event_id else None
    if ev is None or ev.organization_id != auth.org_id:
        raise ApiError(404, "run_not_found", "Exécution introuvable")
    if ev.status not in (OutboxStatus.DEAD_LETTER.value, OutboxStatus.RETRYING.value):
        raise ApiError(409, "not_retryable", f"L'événement est {ev.status} : reprise manuelle impossible")
    outbox.requeue(db, ev, actor_ref=auth.actor_ref)
    db.commit()
    return {"event_id": str(ev.id), "status": ev.status}


# --- Brouillons ---------------------------------------------------------------------------------
@router.get("/followups", response_model=Page[FollowupReviewItem], summary="Brouillons à examiner")
def list_followups(db: Db, auth: Auth, status: Literal["DRAFT", "APPROVED", "REJECTED"] | None = None,
                   page: PageQ = 1, page_size: SizeQ = 20):
    return views.list_followups(db, auth.org_id, status=status, page=page, page_size=page_size)


@router.get("/followups/{followup_id}/history", response_model=list[AuditOut], summary="Historique des décisions")
def followup_history(followup_id: uuid.UUID, db: Db, auth: Auth):
    return views.followup_history(db, auth.org_id, followup_id)


@router.patch("/followups/{followup_id}", response_model=FollowupOut, summary="Modifier un brouillon")
def patch_followup(followup_id: uuid.UUID, body: FollowupPatch, db: Db, auth: Auth):
    if body.subject is None and body.body is None:
        raise ApiError(422, "empty_patch", "Aucune modification fournie")
    f = followup_svc.edit_draft(db, followup_id, auth.org_id, subject=body.subject, body=body.body,
                                expected_version=body.expected_version, actor_ref=auth.actor_ref)
    db.commit()
    return FollowupOut.model_validate(f)


@router.post("/followups/{followup_id}/approve", response_model=FollowupOut,
             summary="Approuver un brouillon (n'envoie AUCUN e-mail)")
def approve_followup(followup_id: uuid.UUID, db: Db, auth: Auth, body: FollowupDecision | None = None):
    f = followup_svc.approve(db, followup_id, auth.org_id, actor_ref=auth.actor_ref,
                             expected_version=body.expected_version if body else None)
    db.commit()
    return FollowupOut.model_validate(f)


@router.post("/followups/{followup_id}/reject", response_model=FollowupOut, summary="Rejeter un brouillon")
def reject_followup(followup_id: uuid.UUID, db: Db, auth: Auth, body: FollowupDecision | None = None):
    f = followup_svc.reject(db, followup_id, auth.org_id, actor_ref=auth.actor_ref, reason=body.reason if body else None)
    db.commit()
    return FollowupOut.model_validate(f)
