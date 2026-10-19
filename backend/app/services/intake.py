"""Réception d'une demande publique : idempotence, anti-abus, dédup contact, lead + outbox atomiques."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import EventType, LeadStatus
from app.core.errors import ApiError
from app.models import Contact, IntakeEvent, Lead, Organization
from app.schemas.public import LeadCreate, LeadReceipt
from app.services import outbox
from app.services.common import advisory_lock, audit, normalize_email, request_hash

IP_WINDOW = timedelta(hours=1)


def hash_ip(ip: str | None) -> str | None:
    """HMAC de l'IP : permet le rate limit sans stocker l'adresse en clair."""
    if not ip:
        return None
    key = get_settings().session_secret.get_secret_value().encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


def get_default_org(db: Session) -> Organization:
    slug = get_settings().default_org_slug
    org = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
    if org is None:
        raise ApiError(503, "organization_not_initialized", "Organisation non initialisée (lancer le seed)")
    return org


def submit_lead(db: Session, *, org: Organization, payload: LeadCreate, idempotency_key: uuid.UUID,
                client_ip_hash: str | None) -> tuple[LeadReceipt, bool]:
    """Retourne (reçu, rejeu?). Une seule transaction : contact + lead + intake + outbox + audit."""
    settings = get_settings()
    body_hash = request_hash(payload.canonical())

    # Sérialise les requêtes portant la même clé : le second appel verra le résultat du premier.
    advisory_lock(db, f"public-lead:{org.id}:{idempotency_key}")

    existing = db.execute(
        select(IntakeEvent).where(IntakeEvent.organization_id == org.id, IntakeEvent.client_request_id == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_body_hash != body_hash:
            audit(db, org_id=org.id, lead_id=existing.lead_id, action="intake.idempotency_conflict",
                  metadata={"client_request_id": str(idempotency_key)})
            db.commit()
            raise ApiError(409, "idempotency_key_reuse", "Idempotency-Key déjà utilisée avec un contenu différent")
        # Même résultat qu'à la création (le statut courant du lead se consulte via le dashboard).
        return LeadReceipt(lead_id=existing.lead_id, status=LeadStatus.NEW.value, request_id=existing.id), True

    # Anti-abus : plafond par IP (hachée) sur une heure glissante, persistant à travers les redémarrages.
    if client_ip_hash:
        since = datetime.now(UTC) - IP_WINDOW
        count = db.execute(
            select(func.count()).select_from(IntakeEvent).where(
                IntakeEvent.client_ip_hash == client_ip_hash, IntakeEvent.created_at >= since
            )
        ).scalar_one()
        if count >= settings.public_rate_limit_per_hour:
            raise ApiError(429, "rate_limited", "Trop de demandes, réessayez plus tard",
                           headers={"Retry-After": str(int(IP_WINDOW.total_seconds()))})

    email_norm = normalize_email(str(payload.email))
    now = datetime.now(UTC)
    marketing = payload.consent_marketing
    insert = pg_insert(Contact).values(
        id=uuid.uuid4(),
        organization_id=org.id,
        full_name=payload.full_name,
        email=str(payload.email).strip(),
        email_normalized=email_norm,
        company=payload.company,
        phone=payload.phone,
        consent_status="granted" if marketing else "unknown",
        consent_at=now if marketing else None,
    )
    # Un seul contact par (organisation, e-mail normalisé) même en cas de soumissions concurrentes.
    contact_id = db.execute(
        insert.on_conflict_do_update(
            index_elements=["organization_id", "email_normalized"],
            set_={
                "full_name": insert.excluded.full_name,
                "company": func.coalesce(insert.excluded.company, Contact.company),
                "phone": func.coalesce(insert.excluded.phone, Contact.phone),
                "updated_at": func.now(),
                **(
                    {"consent_status": "granted", "consent_at": now}
                    if marketing
                    else {}
                ),
            },
        ).returning(Contact.id)
    ).scalar_one()

    lead = Lead(
        organization_id=org.id,
        contact_id=contact_id,
        source="website",
        requested_service=payload.requested_service,
        message=payload.message,
        status=LeadStatus.NEW.value,
        privacy_consent_at=now,
        privacy_notice_version=settings.privacy_notice_version,
    )
    db.add(lead)
    db.flush()

    intake = IntakeEvent(
        organization_id=org.id,
        lead_id=lead.id,
        client_request_id=idempotency_key,
        request_body_hash=body_hash,
        client_ip_hash=client_ip_hash,
    )
    db.add(intake)
    db.flush()

    ev = outbox.enqueue(
        db,
        org_id=org.id,
        lead_id=lead.id,
        event_type=EventType.LEAD_SUBMITTED,
        dedupe_key=f"lead:{lead.id}:submitted",
        payload={"intake_event_id": str(intake.id), "reason": "submitted"},
    )
    audit(db, org_id=org.id, lead_id=lead.id, action="lead.received", correlation_id=ev.correlation_id,
          metadata={"intake_event_id": str(intake.id), "source": "website"})
    audit(db, org_id=org.id, lead_id=lead.id, action="lead.validated", correlation_id=ev.correlation_id,
          metadata={"checks": ["schema", "email_normalized", "size_limits", "consent_privacy"]})
    db.commit()
    return LeadReceipt(lead_id=lead.id, status=lead.status, request_id=intake.id), False
