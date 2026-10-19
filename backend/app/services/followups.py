"""Brouillons : contexte, génération IA, création idempotente, édition / approbation / rejet humains.

AUCUN envoi : ce module ne contient aucun code d'expédition et la base interdit READY_TO_SEND / SENT.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import SERVICE_CATALOG, FollowupStatus, LeadStatus
from app.core.errors import ApiError
from app.integrations.llm.base import DraftRequest, LlmError
from app.integrations.llm.factory import get_llm_provider
from app.models import Contact, Followup, Lead
from app.schemas.extraction import DraftOutput
from app.services import llm_usage
from app.services.common import audit
from app.services.draft_policy import check_draft_policy
from app.services.lead_state import transition
from app.services.qualification import latest_qualification


def draft_context(db: Session, lead: Lead) -> dict[str, Any]:
    q = latest_qualification(db, lead.id)
    if q is None:
        raise ApiError(409, "lead_not_qualified", "Le lead n'est pas encore qualifié")
    contact = db.get(Contact, lead.contact_id)
    return {
        "lead_id": str(lead.id),
        "lead_status": lead.status,
        "qualification_version": q.version,
        "language": q.language,
        "service": q.service,
        "summary": q.summary,
        "has_open_draft": db.execute(
            select(Followup.id).where(
                Followup.lead_id == lead.id,
                Followup.status.in_([FollowupStatus.DRAFT.value, FollowupStatus.APPROVED.value]),
            ).limit(1)
        ).first() is not None,
        "company": contact.company,
    }


def _build_request(db: Session, lead: Lead) -> tuple[DraftRequest, float | None]:
    q = latest_qualification(db, lead.id)
    if q is None:
        raise ApiError(409, "lead_not_qualified", "Le lead n'est pas encore qualifié")
    contact = db.get(Contact, lead.contact_id)
    service = q.service if q.service in SERVICE_CATALOG else (
        lead.requested_service if lead.requested_service in SERVICE_CATALOG else None)
    lang = q.language if q.language in ("fr", "en", "es", "de", "it", "pt") else "fr"
    label = (SERVICE_CATALOG[service].label_en if lang == "en" else SERVICE_CATALOG[service].label_fr) if service else (
        "your request" if lang == "en" else "votre demande")
    budget = float(q.budget_amount) if q.budget_amount is not None else None
    req = DraftRequest(
        first_name=contact.full_name.split()[0][:40],
        company=contact.company,
        language=lang,
        service_id=service,
        service_label=label,
        summary=q.summary or "",
        evidence=list((q.extracted_data or {}).get("evidence", []))[:3],
        budget_amount=budget,
        budget_currency=q.budget_currency,
        timeline_days=q.timeline_days,
    )
    return req, budget


def generate(db: Session, lead: Lead) -> dict[str, Any]:
    req, budget = _build_request(db, lead)
    provider = get_llm_provider()
    llm_usage.check_budget(db)
    try:
        result = provider.draft(req)
    except LlmError as exc:
        llm_usage.record_failure(db, lead_id=lead.id, kind="draft", provider=provider.name, model=provider.model, exc=exc)
        db.commit()
        raise
    llm_usage.record_success(db, lead_id=lead.id, kind="draft", result=result)
    policy = check_draft_policy(result.output.subject, result.output.body, allowed_budget=budget)
    if not policy.ok:
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="draft.policy_violation", is_demo=lead.is_demo,
              metadata={"violations": policy.violations, "model": result.model, "prompt_version": result.prompt_version})
        return {"ok": False, "error_code": "DRAFT_POLICY_VIOLATION", "violations": policy.violations}
    return {
        "ok": True,
        "draft": result.output.model_dump(mode="json"),
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "usage": {"input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens},
    }


def create_draft(db: Session, lead: Lead, *, event_id: uuid.UUID, draft: DraftOutput, provider: str | None,
                 model_name: str | None, prompt_version: str | None) -> dict[str, Any]:
    existing = db.execute(select(Followup).where(Followup.creation_event_id == event_id)).scalar_one_or_none()
    if existing is not None:
        return followup_brief(existing, replayed=True)
    q = latest_qualification(db, lead.id)
    if q is None:
        raise ApiError(409, "lead_not_qualified", "Le lead n'est pas encore qualifié")
    budget = float(q.budget_amount) if q.budget_amount is not None else None
    policy = check_draft_policy(draft.subject, draft.body, allowed_budget=budget)
    if not policy.ok:  # défense en profondeur : le contrôle est refait avant toute écriture
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="draft.policy_violation", is_demo=lead.is_demo,
              metadata={"violations": policy.violations, "stage": "create"})
        db.commit()
        raise ApiError(422, "draft_policy_violation", "Le brouillon viole la politique de contenu",
                       {"violations": policy.violations})
    f = Followup(
        lead_id=lead.id, qualification_id=q.id, subject=draft.subject, body=draft.body, language=draft.language,
        status=FollowupStatus.DRAFT.value, creation_event_id=event_id, llm_provider=provider, model_name=model_name,
        prompt_version=prompt_version, is_demo=lead.is_demo,
    )
    db.add(f)
    db.flush()
    if lead.status == LeadStatus.QUALIFIED.value:
        transition(db, lead, LeadStatus.READY, reason="draft_created")
    audit(db, org_id=lead.organization_id, lead_id=lead.id, action="draft.created", is_demo=lead.is_demo,
          metadata={"followup_id": str(f.id), "model": model_name, "prompt_version": prompt_version})
    return followup_brief(f)


def followup_brief(f: Followup, *, replayed: bool = False) -> dict[str, Any]:
    return {"followup_id": str(f.id), "status": f.status, "lead_id": str(f.lead_id), "replayed": replayed}


# --- Actions humaines (dashboard) -----------------------------------------------------------------
def _locked(db: Session, followup_id: uuid.UUID, org_id: uuid.UUID) -> tuple[Followup, Lead]:
    f = db.execute(select(Followup).where(Followup.id == followup_id).with_for_update()).scalar_one_or_none()
    lead = db.get(Lead, f.lead_id) if f else None
    if f is None or lead is None or lead.organization_id != org_id:
        raise ApiError(404, "followup_not_found", "Brouillon introuvable")
    return f, lead


def _require_draft(f: Followup) -> None:
    if f.status != FollowupStatus.DRAFT.value:
        raise ApiError(409, "followup_not_editable", f"Le brouillon est déjà {f.status}")


def edit_draft(db: Session, followup_id: uuid.UUID, org_id: uuid.UUID, *, subject: str | None, body: str | None,
               expected_version: int | None, actor_ref: str) -> Followup:
    f, lead = _locked(db, followup_id, org_id)
    _require_draft(f)
    if expected_version is not None and expected_version != f.edit_version:
        raise ApiError(409, "edit_conflict", "Le brouillon a été modifié entre-temps", {"current_version": f.edit_version})
    changed = []
    if subject is not None and subject != f.subject:
        f.subject = subject
        changed.append("subject")
    if body is not None and body != f.body:
        f.body = body
        changed.append("body")
    if changed:
        f.edit_version += 1
        f.edited_by = actor_ref
        f.edited_at = datetime.now(UTC)
        audit(db, org_id=org_id, lead_id=lead.id, action="draft.edited", actor_type="user", actor_ref=actor_ref,
              is_demo=lead.is_demo, metadata={"followup_id": str(f.id), "fields": changed, "version": f.edit_version})
    return f


def approve(db: Session, followup_id: uuid.UUID, org_id: uuid.UUID, *, actor_ref: str, expected_version: int | None) -> Followup:
    f, lead = _locked(db, followup_id, org_id)
    if f.status == FollowupStatus.APPROVED.value:
        return f  # idempotent : double clic sans effet
    _require_draft(f)
    if expected_version is not None and expected_version != f.edit_version:
        raise ApiError(409, "edit_conflict", "Le brouillon a été modifié entre-temps", {"current_version": f.edit_version})
    f.status = FollowupStatus.APPROVED.value  # jamais READY_TO_SEND / SENT, et aucun envoi n'est déclenché
    f.approved_by = actor_ref
    f.approved_at = datetime.now(UTC)
    audit(db, org_id=org_id, lead_id=lead.id, action="draft.approved", actor_type="user", actor_ref=actor_ref,
          is_demo=lead.is_demo, metadata={"followup_id": str(f.id), "version": f.edit_version, "sent": False})
    return f


def reject(db: Session, followup_id: uuid.UUID, org_id: uuid.UUID, *, actor_ref: str, reason: str | None) -> Followup:
    f, lead = _locked(db, followup_id, org_id)
    if f.status == FollowupStatus.REJECTED.value:
        return f
    _require_draft(f)
    f.status = FollowupStatus.REJECTED.value
    f.rejected_by = actor_ref
    f.rejected_at = datetime.now(UTC)
    f.reject_reason = reason
    audit(db, org_id=org_id, lead_id=lead.id, action="draft.rejected", actor_type="user", actor_ref=actor_ref,
          is_demo=lead.is_demo, metadata={"followup_id": str(f.id), "reason": reason})
    return f
