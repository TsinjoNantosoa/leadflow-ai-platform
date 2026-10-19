"""Extraction IA (via fournisseur LLM), qualification (scoring serveur) et passage en revue manuelle."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import EventType, FollowupStatus, LeadStatus
from app.core.errors import ApiError
from app.integrations.llm.base import ExtractionRequest, LlmError
from app.integrations.llm.factory import get_llm_provider
from app.models import Contact, Followup, Lead, Qualification
from app.schemas.extraction import LeadExtraction
from app.services import llm_usage, outbox
from app.services.common import audit
from app.services.extraction_checks import check_extraction
from app.services.lead_state import transition
from app.services.scoring import ScoringInput, compute_score


def get_lead(db: Session, lead_id: uuid.UUID, *, for_update: bool = False) -> Lead:
    stmt = select(Lead).where(Lead.id == lead_id)
    if for_update:
        stmt = stmt.with_for_update()
    lead = db.execute(stmt).scalar_one_or_none()
    if lead is None:
        raise ApiError(404, "lead_not_found", "Lead introuvable")
    return lead


def latest_qualification(db: Session, lead_id: uuid.UUID) -> Qualification | None:
    return db.execute(
        select(Qualification).where(Qualification.lead_id == lead_id).order_by(Qualification.version.desc()).limit(1)
    ).scalar_one_or_none()


def qualification_for_event(db: Session, event_id: uuid.UUID) -> Qualification | None:
    return db.execute(select(Qualification).where(Qualification.source_event_id == event_id)).scalar_one_or_none()


def lead_payload(db: Session, lead: Lead, event_id: uuid.UUID | None) -> dict[str, Any]:
    """Données strictement nécessaires à n8n pour décider (le texte du prospect n'est PAS transmis)."""
    q = latest_qualification(db, lead.id)
    already = bool(event_id and qualification_for_event(db, event_id))
    return {
        "lead_id": str(lead.id),
        "status": lead.status,
        "requested_service": lead.requested_service,
        "has_qualification": q is not None,
        "qualification_version": q.version if q else None,
        "already_qualified_for_event": already,
    }


def extract(db: Session, lead: Lead) -> dict[str, Any]:
    """Appelle le LLM pour extraire les faits du message. Ne persiste rien d'autre que l'usage (traçabilité)."""
    provider = get_llm_provider()
    llm_usage.check_budget(db)
    try:
        result = provider.extract(ExtractionRequest(message=lead.message, requested_service=lead.requested_service))
    except LlmError as exc:
        llm_usage.record_failure(db, lead_id=lead.id, kind="extraction", provider=provider.name,
                                 model=provider.model, exc=exc)
        db.commit()  # la trace de l'échec doit survivre à la réponse d'erreur
        raise
    cleaned, reasons = check_extraction(result.output, lead.message)
    llm_usage.record_success(db, lead_id=lead.id, kind="extraction", result=result)
    audit(db, org_id=lead.organization_id, lead_id=lead.id, action="ai.extraction_completed", is_demo=lead.is_demo,
          metadata={"provider": result.provider, "model": result.model, "prompt_version": result.prompt_version,
                    "review_reasons": reasons, "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens})
    return {
        "ok": True,
        "extraction": cleaned.model_dump(mode="json"),
        "review_reasons": reasons,
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "usage": {"input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens},
    }


def save_qualification(db: Session, lead: Lead, *, event_id: uuid.UUID, extraction: LeadExtraction,
                       provider: str | None, model_name: str | None, prompt_version: str | None) -> dict[str, Any]:
    existing = qualification_for_event(db, event_id)
    if existing is not None:
        return qualification_summary(existing, lead.status, replayed=True)

    # La sortie est re-contrôlée côté serveur : on ne fait pas confiance au transport (n8n) ni au LLM.
    cleaned, reasons = check_extraction(extraction, lead.message)
    contact = db.get(Contact, lead.contact_id)
    score = compute_score(
        ScoringInput(
            full_name=contact.full_name, email=contact.email, company=contact.company,
            requested_service=lead.requested_service, extraction=cleaned,
        )
    )
    version = (db.execute(select(func.max(Qualification.version)).where(Qualification.lead_id == lead.id)).scalar() or 0) + 1
    needs_review = bool(reasons)
    q = Qualification(
        lead_id=lead.id,
        version=version,
        source_event_id=event_id,
        intent=cleaned.intent,
        service=cleaned.service,
        budget_amount=cleaned.budget_amount,
        budget_currency=cleaned.budget_currency,
        timeline_days=cleaned.timeline_days,
        language=cleaned.language,
        summary=cleaned.summary,
        need_clarity=cleaned.need_clarity,
        score=score.score,
        segment=score.segment,
        score_explanation=score.explanation(),
        extracted_data=cleaned.model_dump(mode="json"),
        llm_provider=provider,
        model_name=model_name,
        prompt_version=prompt_version,
        scoring_rule_version=score.rule_version,
        human_review_required=needs_review,
        review_reasons=reasons,
    )
    db.add(q)
    db.flush()

    transition(db, lead, LeadStatus.PROCESSING, strict=False)
    target = LeadStatus.MANUAL_REVIEW if needs_review else LeadStatus.QUALIFIED
    transition(db, lead, target, reason=",".join(reasons) or None)
    audit(db, org_id=lead.organization_id, lead_id=lead.id, action="lead.qualified", is_demo=lead.is_demo,
          metadata={"qualification_id": str(q.id), "version": version, "score": score.score, "segment": score.segment,
                    "rule_version": score.rule_version, "review_reasons": reasons})

    emitted = _emit_followup_events(db, lead, version, injection="prompt_injection_suspected" in reasons)
    return qualification_summary(q, lead.status, emitted=emitted)


def _emit_followup_events(db: Session, lead: Lead, version: int, *, injection: bool) -> list[str]:
    emitted: list[str] = []
    ev = outbox.enqueue(db, org_id=lead.organization_id, lead_id=lead.id, event_type=EventType.CRM_SYNC_REQUESTED,
                        dedupe_key=f"lead:{lead.id}:q{version}:crm", payload={"qualification_version": version},
                        is_demo=lead.is_demo)
    emitted.append(ev.event_type)
    open_draft = db.execute(
        select(func.count()).select_from(Followup).where(
            Followup.lead_id == lead.id,
            Followup.status.in_([FollowupStatus.DRAFT.value, FollowupStatus.APPROVED.value]),
        )
    ).scalar_one()
    if injection:
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="draft.skipped", is_demo=lead.is_demo,
              metadata={"reason": "prompt_injection_suspected"})
    elif open_draft:
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="draft.skipped", is_demo=lead.is_demo,
              metadata={"reason": "open_draft_exists"})
    else:
        ev = outbox.enqueue(db, org_id=lead.organization_id, lead_id=lead.id, event_type=EventType.DRAFT_REQUESTED,
                            dedupe_key=f"lead:{lead.id}:q{version}:draft", payload={"qualification_version": version},
                            is_demo=lead.is_demo)
        emitted.append(ev.event_type)
    return emitted


def qualification_summary(q: Qualification, lead_status: str, *, replayed: bool = False,
                          emitted: list[str] | None = None) -> dict[str, Any]:
    return {
        "qualification_id": str(q.id),
        "version": q.version,
        "score": q.score,
        "segment": q.segment,
        "human_review_required": q.human_review_required,
        "review_reasons": q.review_reasons,
        "lead_status": lead_status,
        "emitted_events": emitted or [],
        "replayed": replayed,
    }


def mark_manual_review(db: Session, lead: Lead, *, error_code: str, detail: str | None) -> dict[str, Any]:
    transition(db, lead, LeadStatus.PROCESSING, strict=False)
    transition(db, lead, LeadStatus.MANUAL_REVIEW, reason=error_code)
    audit(db, org_id=lead.organization_id, lead_id=lead.id, action="lead.manual_review_required", is_demo=lead.is_demo,
          metadata={"error_code": error_code, "detail": (detail or "")[:300]})
    return {"lead_status": lead.status, "error_code": error_code}
