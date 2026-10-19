"""CRM : contexte de synchronisation, CRM factice idempotent, enregistrement du résultat (mapping)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import SERVICE_CATALOG, CrmSyncStatus
from app.core.errors import ApiError
from app.models import Contact, CrmMapping, Lead, MockCrmContact
from app.services.common import audit
from app.services.qualification import latest_qualification


def crm_context(db: Session, lead: Lead) -> dict[str, Any]:
    contact = db.get(Contact, lead.contact_id)
    provider = get_settings().crm_provider
    mapping = db.execute(
        select(CrmMapping).where(
            CrmMapping.organization_id == lead.organization_id,
            CrmMapping.contact_id == lead.contact_id,
            CrmMapping.provider == provider,
        )
    ).scalar_one_or_none()
    q = latest_qualification(db, lead.id)
    service = q.service if q else lead.requested_service
    return {
        "provider": provider,
        "contact": {
            "contact_id": str(contact.id),
            "email": contact.email,
            "email_normalized": contact.email_normalized,
            "full_name": contact.full_name,
            "company": contact.company,
            "phone": contact.phone,
        },
        "mapping": None
        if mapping is None
        else {
            "external_contact_id": mapping.external_contact_id,
            "sync_status": mapping.sync_status,
            "attempt_count": mapping.attempt_count,
        },
        "qualification": None
        if q is None
        else {
            "score": q.score,
            "segment": q.segment,
            "service": service,
            "service_label": SERVICE_CATALOG[service].label_fr if service in SERVICE_CATALOG else None,
            "summary": q.summary,
        },
    }


def mock_upsert(db: Session, lead: Lead) -> dict[str, Any]:
    """Simule HubSpot : recherche par e-mail normalisé puis création/mise à jour, de façon idempotente."""
    contact = db.get(Contact, lead.contact_id)
    ext_id = "mock_" + uuid.uuid5(uuid.NAMESPACE_URL, f"{lead.organization_id}:{contact.email_normalized}").hex[:16]
    props = {"firstname_lastname": contact.full_name, "company": contact.company, "email": contact.email_normalized}
    stmt = pg_insert(MockCrmContact).values(
        external_id=ext_id, organization_id=lead.organization_id, email_normalized=contact.email_normalized,
        properties=props,
    )
    row = db.execute(
        stmt.on_conflict_do_update(
            index_elements=["organization_id", "email_normalized"],
            set_={"properties": stmt.excluded.properties, "updated_at": func.now()},
        ).returning(MockCrmContact.external_id, literal_column("(xmax = 0)").label("inserted"))
    ).one()  # xmax = 0 <=> ligne insérée (et non mise à jour) par cette requête
    return {"external_contact_id": row.external_id, "action": "created" if row.inserted else "updated", "provider": "mock"}


def record_sync(db: Session, lead: Lead, *, event_id: uuid.UUID, provider: str, status: CrmSyncStatus,
                external_contact_id: str | None, error_code: str | None, action: str | None) -> dict[str, Any]:
    mapping = db.execute(
        select(CrmMapping).where(
            CrmMapping.organization_id == lead.organization_id,
            CrmMapping.contact_id == lead.contact_id,
            CrmMapping.provider == provider,
        ).with_for_update()
    ).scalar_one_or_none()
    if mapping is None:
        db.execute(
            pg_insert(CrmMapping)
            .values(organization_id=lead.organization_id, contact_id=lead.contact_id, provider=provider)
            .on_conflict_do_nothing(constraint="uq_crm_org_contact_provider")
        )
        mapping = db.execute(
            select(CrmMapping).where(
                CrmMapping.organization_id == lead.organization_id,
                CrmMapping.contact_id == lead.contact_id,
                CrmMapping.provider == provider,
            ).with_for_update()
        ).scalar_one()

    if external_contact_id and mapping.external_contact_id and mapping.external_contact_id != external_contact_id:
        # Garde-fou anti-doublon CRM : un même contact ne doit jamais pointer vers deux fiches externes.
        audit(db, org_id=lead.organization_id, lead_id=lead.id, action="crm.external_id_conflict", is_demo=lead.is_demo,
              metadata={"provider": provider, "known": mapping.external_contact_id, "received": external_contact_id})
        db.commit()
        raise ApiError(409, "crm_external_id_conflict", "Ce contact est déjà lié à une autre fiche CRM")

    mapping.attempt_count += 1
    mapping.sync_status = status.value
    mapping.last_event_id = event_id
    mapping.last_error_code = None if status == CrmSyncStatus.SYNCED else (error_code or "UNKNOWN")
    if external_contact_id:
        mapping.external_contact_id = external_contact_id
    if status == CrmSyncStatus.SYNCED:
        mapping.last_synced_at = datetime.now(UTC)
    audit(db, org_id=lead.organization_id, lead_id=lead.id, is_demo=lead.is_demo,
          action="crm.synced" if status == CrmSyncStatus.SYNCED else "crm.sync_failed",
          metadata={"provider": provider, "status": status.value, "error_code": error_code, "action": action,
                    "attempt": mapping.attempt_count, "external_contact_id": mapping.external_contact_id})
    return {
        "provider": provider,
        "sync_status": mapping.sync_status,
        "external_contact_id": mapping.external_contact_id,
        "attempt_count": mapping.attempt_count,
    }
