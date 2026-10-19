"""Export / suppression des données d'un contact (droits d'accès et d'effacement). Opération manuelle d'un admin.

    python -m scripts.contact_data export --email alice@example.org > export.json
    python -m scripts.contact_data delete --email alice@example.org            # simulation
    python -m scripts.contact_data delete --email alice@example.org --apply    # effacement effectif

La suppression retire le contact, ses leads, qualifications, brouillons, mappings CRM, événements outbox, runs et audits
associés. Une trace minimale (`privacy.contact_erased`, sans donnée personnelle) est conservée dans l'audit.
Elle ne supprime PAS la fiche dans HubSpot : à faire séparément dans le CRM.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import delete, select

from app.database.session import get_sessionmaker
from app.models import (
    AuditEvent,
    AutomationRun,
    Contact,
    CrmMapping,
    Followup,
    IntakeEvent,
    Lead,
    LlmUsage,
    MockCrmContact,
    OutboxEvent,
    Qualification,
)
from app.services.common import audit, normalize_email


def _rows(db, model, cond):
    return [{c.name: str(getattr(r, c.key)) if getattr(r, c.key) is not None else None for c in model.__table__.columns}
            for r in db.execute(select(model).where(cond)).scalars()]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["export", "delete"])
    p.add_argument("--email", required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    email = normalize_email(args.email)

    with get_sessionmaker()() as db:
        contacts = db.execute(select(Contact).where(Contact.email_normalized == email)).scalars().all()
        if not contacts:
            sys.exit("Aucun contact pour cet e-mail.")
        for c in contacts:
            lead_ids = list(db.execute(select(Lead.id).where(Lead.contact_id == c.id)).scalars())
            if args.action == "export":
                out = {
                    "contact": _rows(db, Contact, Contact.id == c.id),
                    "leads": _rows(db, Lead, Lead.contact_id == c.id),
                    "qualifications": _rows(db, Qualification, Qualification.lead_id.in_(lead_ids)),
                    "followups": _rows(db, Followup, Followup.lead_id.in_(lead_ids)),
                    "crm_mappings": _rows(db, CrmMapping, CrmMapping.contact_id == c.id),
                    "audit_events": _rows(db, AuditEvent, AuditEvent.lead_id.in_(lead_ids)),
                }
                print(json.dumps(out, ensure_ascii=False, indent=2))
                continue
            print(f"[erase] contact {c.id}: {len(lead_ids)} lead(s) {'SUPPRIMÉ(S)' if args.apply else '(simulation)'}")
            if not args.apply:
                continue
            org_id = c.organization_id
            db.execute(delete(Followup).where(Followup.lead_id.in_(lead_ids)))
            db.execute(delete(Qualification).where(Qualification.lead_id.in_(lead_ids)))
            db.execute(delete(AutomationRun).where(AutomationRun.lead_id.in_(lead_ids)))
            db.execute(delete(OutboxEvent).where(OutboxEvent.lead_id.in_(lead_ids)))
            db.execute(delete(LlmUsage).where(LlmUsage.lead_id.in_(lead_ids)))
            db.execute(delete(AuditEvent).where(AuditEvent.lead_id.in_(lead_ids)))
            db.execute(delete(IntakeEvent).where(IntakeEvent.lead_id.in_(lead_ids)))
            db.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
            db.execute(delete(CrmMapping).where(CrmMapping.contact_id == c.id))
            db.execute(delete(MockCrmContact).where(MockCrmContact.email_normalized == email))
            db.execute(delete(Contact).where(Contact.id == c.id))
            audit(db, org_id=org_id, action="privacy.contact_erased", actor_type="user", actor_ref="cli-admin",
                  metadata={"leads_erased": len(lead_ids)})
        db.commit()


if __name__ == "__main__":
    main()
