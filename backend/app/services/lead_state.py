"""Machine à états du lead : toute transition invalide => 409 + audit."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import LeadStatus as S
from app.core.errors import ApiError
from app.models import Lead
from app.services.common import audit

ALLOWED: dict[str, set[str]] = {
    S.NEW: {S.PROCESSING, S.MANUAL_REVIEW, S.FAILED, S.ARCHIVED},
    S.PROCESSING: {S.QUALIFIED, S.MANUAL_REVIEW, S.FAILED, S.ARCHIVED},
    S.QUALIFIED: {S.READY, S.MANUAL_REVIEW, S.FAILED, S.PROCESSING, S.ARCHIVED},
    S.MANUAL_REVIEW: {S.PROCESSING, S.QUALIFIED, S.FAILED, S.ARCHIVED},
    S.READY: {S.PROCESSING, S.MANUAL_REVIEW, S.ARCHIVED},
    S.FAILED: {S.PROCESSING, S.ARCHIVED},
    S.ARCHIVED: set(),
}


def can_transition(current: str, new: str) -> bool:
    return new in {s.value for s in ALLOWED.get(current, set())}


def transition(db: Session, lead: Lead, new: S, *, reason: str | None = None, actor_type: str = "system",
               actor_ref: str | None = None, strict: bool = True) -> bool:
    """Applique la transition. `strict=False` : ignore silencieusement une transition sans effet (même statut)."""
    if lead.status == new.value:
        return False
    if not can_transition(lead.status, new.value):
        if not strict:
            return False
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="lead.invalid_transition",
              actor_type=actor_type, actor_ref=actor_ref, is_demo=lead.is_demo,
              metadata={"from": lead.status, "to": new.value})
        db.commit()  # le journal d'audit de l'erreur métier survit au 409
        raise ApiError(409, "invalid_transition", f"Transition {lead.status} -> {new.value} impossible")
    audit(db, org_id=lead.organization_id, lead_id=lead.id, action="lead.status_changed",
          actor_type=actor_type, actor_ref=actor_ref, is_demo=lead.is_demo,
          metadata={"from": lead.status, "to": new.value, "reason": reason})
    lead.status = new.value
    lead.status_reason = reason
    return True
