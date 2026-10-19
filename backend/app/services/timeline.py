"""Timeline d'un lead : chaque étape est dérivée d'enregistrements réels, jamais simulée."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.constants import FollowupStatus, LeadStatus
from app.models import AuditEvent, CrmMapping, Followup, Lead, Qualification
from app.schemas.dashboard import TimelineStep


def _first_audit(audits: Sequence[AuditEvent], action: str) -> AuditEvent | None:
    matches = [a for a in audits if a.action == action]
    return min(matches, key=lambda a: a.created_at) if matches else None


def build_timeline(lead: Lead, quals: Sequence[Qualification], mapping: CrmMapping | None,
                   followups: Sequence[Followup], audits: Sequence[AuditEvent]) -> list[TimelineStep]:
    steps: list[TimelineStep] = []
    q = quals[0] if quals else None  # la plus récente
    failed = lead.status == LeadStatus.FAILED.value

    steps.append(TimelineStep(key="lead_received", label="Demande reçue", state="done", at=lead.created_at,
                              detail=f"Source : {lead.source}"))
    validated = _first_audit(audits, "lead.validated")
    steps.append(TimelineStep(key="validated", label="Validation", state="done",
                              at=validated.created_at if validated else lead.created_at,
                              detail="Données validées et enregistrées"))

    if q:
        steps.append(TimelineStep(key="ai_qualification", label="Qualification IA", state="done", at=q.created_at,
                                  detail=f"{q.llm_provider or '—'} · {q.model_name or '—'} · {q.prompt_version or '—'}"
                                  + (" · revue humaine requise" if q.human_review_required else "")))
        steps.append(TimelineStep(key="scoring", label="Scoring", state="done", at=q.created_at,
                                  detail=f"{q.score}/100 · {q.segment} · {q.scoring_rule_version}"))
    else:
        mr = _first_audit(audits, "lead.manual_review_required")
        if mr is not None:
            code = (mr.event_metadata or {}).get("error_code")
            steps.append(TimelineStep(key="ai_qualification", label="Qualification IA", state="attention",
                                      at=mr.created_at, detail=f"Revue manuelle requise ({code})"))
        elif failed:
            steps.append(TimelineStep(key="ai_qualification", label="Qualification IA", state="failed", at=None,
                                      detail=lead.status_reason or "Échec du traitement"))
        else:
            in_progress = lead.status == LeadStatus.PROCESSING.value
            steps.append(TimelineStep(key="ai_qualification", label="Qualification IA",
                                      state="in_progress" if in_progress else "pending", at=None))
        steps.append(TimelineStep(key="scoring", label="Scoring", state="pending", at=None))

    if mapping is None or mapping.sync_status == "PENDING":
        steps.append(TimelineStep(key="crm_sync", label="Synchronisation CRM", state="pending", at=None))
    elif mapping.sync_status == "SYNCED":
        steps.append(TimelineStep(key="crm_sync", label="Synchronisation CRM", state="done", at=mapping.last_synced_at,
                                  detail=f"{mapping.provider} · {mapping.external_contact_id}"))
    elif mapping.sync_status == "RETRYING":
        steps.append(TimelineStep(key="crm_sync", label="Synchronisation CRM", state="attention", at=mapping.updated_at,
                                  detail=f"Nouvelle tentative prévue ({mapping.last_error_code})"))
    else:
        steps.append(TimelineStep(key="crm_sync", label="Synchronisation CRM", state="failed", at=mapping.updated_at,
                                  detail=f"Échec ({mapping.last_error_code})"))

    latest_f = followups[0] if followups else None
    if latest_f:
        steps.append(TimelineStep(key="draft_generated", label="Brouillon généré", state="done", at=latest_f.created_at,
                                  detail=f"{latest_f.model_name or '—'} · {latest_f.prompt_version or '—'}"))
    else:
        skipped = _first_audit(audits, "draft.skipped")
        violation = _first_audit(audits, "draft.policy_violation")
        if violation:
            steps.append(TimelineStep(key="draft_generated", label="Brouillon généré", state="failed",
                                      at=violation.created_at, detail="Brouillon refusé par la politique de contenu"))
        elif skipped:
            steps.append(TimelineStep(key="draft_generated", label="Brouillon généré", state="skipped",
                                      at=skipped.created_at, detail=(skipped.event_metadata or {}).get("reason")))
        else:
            steps.append(TimelineStep(key="draft_generated", label="Brouillon généré", state="pending", at=None))

    if latest_f is None:
        steps.append(TimelineStep(key="human_review", label="Revue humaine", state="pending", at=None))
        steps.append(TimelineStep(key="decision", label="Décision", state="pending", at=None))
    elif latest_f.status == FollowupStatus.DRAFT.value:
        steps.append(TimelineStep(key="human_review", label="Revue humaine", state="attention", at=latest_f.created_at,
                                  detail="En attente d'un commercial"))
        steps.append(TimelineStep(key="decision", label="Décision", state="pending", at=None))
    else:
        decided_at = latest_f.approved_at or latest_f.rejected_at
        by = latest_f.approved_by or latest_f.rejected_by
        steps.append(TimelineStep(key="human_review", label="Revue humaine", state="done", at=decided_at, detail=by))
        approved = latest_f.status == FollowupStatus.APPROVED.value
        steps.append(TimelineStep(key="decision", label="Approuvé" if approved else "Rejeté", state="done",
                                  at=decided_at, detail="Aucun e-mail envoyé" if approved else latest_f.reject_reason))
    return steps
