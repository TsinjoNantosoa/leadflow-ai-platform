"""Endpoints service-to-service (n8n -> FastAPI). Jamais exposés au navigateur.

Authentification : Bearer API_SERVICE_TOKEN + X-LF-Timestamp (anti-rejeu). Toute mutation exige Idempotency-Key.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import CrmSyncStatus, EventType, OutboxStatus
from app.core.errors import ApiError
from app.database.session import get_db
from app.integrations.llm.base import LlmError
from app.models import AutomationRun, OutboxEvent
from app.schemas.extraction import DraftOutput, LeadExtraction
from app.security.deps import service_auth
from app.services import crm as crm_svc
from app.services import followups as followup_svc
from app.services import outbox
from app.services import qualification as qual_svc
from app.services.common import run_idempotent

router = APIRouter(prefix="/internal", tags=["internal (n8n)"], dependencies=[Depends(service_auth)])
Db = Annotated[Session, Depends(get_db)]


def idem_key(idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    if not idempotency_key or len(idempotency_key) > 128:
        raise ApiError(400, "idempotency_key_required", "En-tête Idempotency-Key requis (<= 128 caractères)")
    return idempotency_key


Key = Annotated[str, Depends(idem_key)]


def _idempotent(db: Session, scope: str, key: str, payload: BaseModel,
                handler: Callable[[], tuple[int, dict[str, Any]]]) -> JSONResponse:
    status, body, replayed = run_idempotent(db, scope=scope, key=key, payload=payload.model_dump(mode="json"),
                                            handler=handler)
    db.commit()
    return JSONResponse(body, status_code=status, headers={"Idempotent-Replayed": "true"} if replayed else None)


def _event_for(db: Session, event_id: uuid.UUID, lead_id: uuid.UUID, types: set[EventType]) -> OutboxEvent:
    ev = db.get(OutboxEvent, event_id)
    if ev is None or ev.lead_id != lead_id or ev.event_type not in {t.value for t in types}:
        raise ApiError(409, "event_mismatch", "L'événement ne correspond pas à ce lead / à cette opération")
    if ev.status != OutboxStatus.PROCESSING.value:
        raise ApiError(409, "event_not_processing", f"L'événement est {ev.status} : la réservation n'est plus valide")
    return ev


# --- Outbox -------------------------------------------------------------------------------------
class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(5, ge=1, le=100)
    worker: str = Field("n8n", max_length=64)


@router.post("/outbox/claim", summary="Réserver atomiquement des événements prêts (lease)")
def claim(body: ClaimIn, db: Db) -> dict[str, Any]:
    claimed = outbox.claim(db, limit=body.limit, worker=body.worker)
    db.commit()
    lease = get_settings().outbox_lease_seconds
    return {
        "lease_seconds": lease,
        "events": [
            {
                "event_id": str(c.event.id), "event_type": c.event.event_type, "workflow": c.run.workflow_name,
                "organization_id": str(c.event.organization_id), "lead_id": str(c.event.lead_id) if c.event.lead_id else None,
                "correlation_id": str(c.event.correlation_id), "attempt": c.event.attempt_count,
                "max_attempts": c.event.max_attempts, "run_id": str(c.run.id), "schema_version": c.event.schema_version,
                "occurred_at": c.event.created_at.isoformat(), "lease_expires_at": c.event.locked_until.isoformat(),
                "payload": c.event.payload,
            }
            for c in claimed
        ],
    }


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt: int = Field(ge=1)
    outcome: Literal["SUCCEEDED", "MANUAL_REVIEW"] = "SUCCEEDED"
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/outbox/{event_id}/complete", summary="Marquer l'événement traité")
def complete(event_id: uuid.UUID, body: CompleteIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        applied, reason = outbox.complete(db, event_id=event_id, attempt=body.attempt, outcome=body.outcome,
                                          details=body.details)
        return 200, {"applied": applied, "reason": reason}

    return _idempotent(db, f"outbox-complete:{event_id}", key, body, handler)


class FailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt: int = Field(ge=1)
    error_code: str = Field(min_length=1, max_length=64)
    retryable: bool
    message: str | None = Field(None, max_length=500)
    retry_after_seconds: int | None = Field(None, ge=0, le=86_400)


@router.post("/outbox/{event_id}/fail", summary="Rapporter un échec : le backend décide retry / dead-letter")
def fail(event_id: uuid.UUID, body: FailIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        applied, reason, extra = outbox.fail(db, event_id=event_id, attempt=body.attempt, error_code=body.error_code,
                                             retryable=body.retryable, message=body.message,
                                             retry_after_seconds=body.retry_after_seconds)
        return 200, {"applied": applied, "reason": reason, **extra}

    return _idempotent(db, f"outbox-fail:{event_id}", key, body, handler)


class RunStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str = Field(min_length=1, max_length=64)
    note: str | None = Field(None, max_length=200)


@router.post("/runs/{run_id}/status", summary="Journaliser une étape d'un run en cours")
def run_step(run_id: uuid.UUID, body: RunStepIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        run = db.execute(select(AutomationRun).where(AutomationRun.id == run_id).with_for_update()).scalar_one_or_none()
        if run is None:
            raise ApiError(404, "run_not_found", "Run introuvable")
        if run.status != "STARTED":
            return 200, {"applied": False, "reason": f"run_{run.status.lower()}"}
        steps = list((run.details or {}).get("steps", []))
        steps.append({"step": body.step, "note": body.note})
        run.details = {**(run.details or {}), "steps": steps[-30:]}
        return 200, {"applied": True, "reason": "applied"}

    return _idempotent(db, f"run-step:{run_id}", key, body, handler)


# --- Qualification ------------------------------------------------------------------------------
@router.get("/leads/{lead_id}/payload", summary="Informations minimales pour le traitement d'un lead")
def lead_payload(lead_id: uuid.UUID, db: Db, event_id: uuid.UUID | None = None) -> dict[str, Any]:
    return qual_svc.lead_payload(db, qual_svc.get_lead(db, lead_id), event_id)


class EventRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID


def _llm_error_response(exc: LlmError) -> JSONResponse:
    """Refus / sortie invalide => 200 `ok:false` (traitement métier : revue manuelle). Panne => 5xx + retryable."""
    if exc.code in ("LLM_REFUSAL", "LLM_INVALID_OUTPUT"):
        return JSONResponse({"ok": False, "error_code": exc.code, "retryable": False}, status_code=200)
    status = 503 if exc.retryable else 502
    return JSONResponse(
        {"error": {"code": exc.code, "message": "Service IA indisponible" if exc.retryable else "Configuration IA invalide",
                   "details": {"retryable": exc.retryable}}},
        status_code=status,
    )


@router.post("/leads/{lead_id}/extract", summary="Extraction structurée par le LLM (OpenAI ou mock)")
def extract(lead_id: uuid.UUID, body: EventRef, db: Db, key: Key) -> JSONResponse:
    lead = qual_svc.get_lead(db, lead_id)
    _event_for(db, body.event_id, lead_id, {EventType.LEAD_SUBMITTED})

    def handler():
        try:
            return 200, qual_svc.extract(db, lead)
        except LlmError as exc:
            raise _Short(_llm_error_response(exc)) from exc

    try:
        return _idempotent(db, f"extract:{lead_id}", key, body, handler)
    except _Short as short:
        return short.response


class _Short(Exception):
    """Court-circuite l'enregistrement idempotent d'une réponse d'erreur (les pannes ne sont pas mémorisées)."""

    def __init__(self, response: JSONResponse):
        self.response = response


class QualificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    extraction: LeadExtraction
    provider: str | None = Field(None, max_length=16)
    model_name: str | None = Field(None, max_length=64)
    prompt_version: str | None = Field(None, max_length=32)


@router.post("/leads/{lead_id}/qualification", summary="Enregistrer la qualification (score calculé côté serveur)")
def qualification(lead_id: uuid.UUID, body: QualificationIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        lead = qual_svc.get_lead(db, lead_id, for_update=True)
        if qual_svc.qualification_for_event(db, body.event_id) is None:
            _event_for(db, body.event_id, lead_id, {EventType.LEAD_SUBMITTED})
        return 200, qual_svc.save_qualification(db, lead, event_id=body.event_id, extraction=body.extraction,
                                                provider=body.provider, model_name=body.model_name,
                                                prompt_version=body.prompt_version)

    return _idempotent(db, f"qualification:{lead_id}", key, body, handler)


class ManualReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    error_code: str = Field(min_length=1, max_length=64)
    detail: str | None = Field(None, max_length=300)


@router.post("/leads/{lead_id}/manual-review", summary="Basculer le lead en revue manuelle")
def manual_review(lead_id: uuid.UUID, body: ManualReviewIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        lead = qual_svc.get_lead(db, lead_id, for_update=True)
        _event_for(db, body.event_id, lead_id, {EventType.LEAD_SUBMITTED})
        return 200, qual_svc.mark_manual_review(db, lead, error_code=body.error_code, detail=body.detail)

    return _idempotent(db, f"manual-review:{lead_id}", key, body, handler)


# --- CRM ----------------------------------------------------------------------------------------
@router.get("/leads/{lead_id}/crm-context", summary="Contact, mapping CRM et CRM_PROVIDER configuré")
def crm_context(lead_id: uuid.UUID, db: Db) -> dict[str, Any]:
    return crm_svc.crm_context(db, qual_svc.get_lead(db, lead_id))


@router.post("/leads/{lead_id}/crm/mock-upsert", summary="CRM factice : upsert idempotent d'un contact")
def mock_upsert(lead_id: uuid.UUID, body: EventRef, db: Db, key: Key) -> JSONResponse:
    if get_settings().crm_provider != "mock":
        raise ApiError(409, "crm_provider_not_mock", "CRM_PROVIDER n'est pas 'mock'")

    def handler():
        lead = qual_svc.get_lead(db, lead_id)
        _event_for(db, body.event_id, lead_id, {EventType.CRM_SYNC_REQUESTED})
        return 200, crm_svc.mock_upsert(db, lead)

    return _idempotent(db, f"crm-mock:{lead_id}", key, body, handler)


class CrmSyncIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    provider: Literal["mock", "hubspot"]
    status: Literal["SYNCED", "RETRYING", "FAILED"]
    external_contact_id: str | None = Field(None, max_length=128)
    error_code: str | None = Field(None, max_length=64)
    action: Literal["created", "updated", "unchanged"] | None = None


@router.post("/leads/{lead_id}/crm-sync", summary="Enregistrer le résultat de la synchronisation CRM")
def crm_sync(lead_id: uuid.UUID, body: CrmSyncIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        if body.provider != get_settings().crm_provider:
            raise ApiError(409, "crm_provider_mismatch", "Le fournisseur ne correspond pas à CRM_PROVIDER")
        if body.status == "SYNCED" and not body.external_contact_id:
            raise ApiError(422, "external_id_required", "external_contact_id requis pour SYNCED")
        lead = qual_svc.get_lead(db, lead_id, for_update=True)
        _event_for(db, body.event_id, lead_id, {EventType.CRM_SYNC_REQUESTED})
        return 200, crm_svc.record_sync(db, lead, event_id=body.event_id, provider=body.provider,
                                        status=CrmSyncStatus(body.status), external_contact_id=body.external_contact_id,
                                        error_code=body.error_code, action=body.action)

    return _idempotent(db, f"crm-sync:{lead_id}", key, body, handler)


# --- Brouillons ---------------------------------------------------------------------------------
@router.get("/leads/{lead_id}/draft-context", summary="Contexte minimal pour la rédaction du brouillon")
def draft_context(lead_id: uuid.UUID, db: Db) -> dict[str, Any]:
    return followup_svc.draft_context(db, qual_svc.get_lead(db, lead_id))


@router.post("/leads/{lead_id}/draft/generate", summary="Générer un brouillon via le LLM (non enregistré)")
def draft_generate(lead_id: uuid.UUID, body: EventRef, db: Db, key: Key) -> JSONResponse:
    lead = qual_svc.get_lead(db, lead_id)
    _event_for(db, body.event_id, lead_id, {EventType.DRAFT_REQUESTED})

    def handler():
        try:
            return 200, followup_svc.generate(db, lead)
        except LlmError as exc:
            raise _Short(_llm_error_response(exc)) from exc

    try:
        return _idempotent(db, f"draft-generate:{lead_id}", key, body, handler)
    except _Short as short:
        return short.response


class FollowupCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: uuid.UUID
    draft: DraftOutput
    provider: str | None = Field(None, max_length=16)
    model_name: str | None = Field(None, max_length=64)
    prompt_version: str | None = Field(None, max_length=32)


@router.post("/leads/{lead_id}/followups", status_code=201, summary="Créer le brouillon (statut DRAFT, idempotent)")
def create_followup(lead_id: uuid.UUID, body: FollowupCreateIn, db: Db, key: Key) -> JSONResponse:
    def handler():
        lead = qual_svc.get_lead(db, lead_id, for_update=True)
        _event_for(db, body.event_id, lead_id, {EventType.DRAFT_REQUESTED})
        return 201, followup_svc.create_draft(db, lead, event_id=body.event_id, draft=body.draft, provider=body.provider,
                                              model_name=body.model_name, prompt_version=body.prompt_version)

    return _idempotent(db, f"followup:{lead_id}", key, body, handler)
