"""Vérifie que la base est à la dernière révision Alembic, sans dérive par rapport aux modèles, et que les
garde-fous SQL critiques existent.  Code de sortie 0 = OK.

    python -m scripts.verify_schema
"""

from __future__ import annotations

import sys

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.models  # noqa: F401
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import build_engine

REQUIRED_CONSTRAINTS = {
    "ck_followups_no_send_in_mvp": "aucun brouillon ne peut être READY_TO_SEND / SENT",
    "ck_qualifications_score_range": "score entre 0 et 100",
    "ck_qualifications_segment_matches_score": "segment cohérent avec les seuils",
    "fk_leads_org_contact": "lead et contact dans la même organisation",
    "uq_contacts_organization_id": "un contact par (organisation, e-mail normalisé)",
    "ck_contacts_email_normalized_canonical": "e-mail normalisé en minuscules",
}
REQUIRED_TABLES = {
    "organizations", "users", "sessions", "contacts", "leads", "intake_events", "qualifications", "crm_mappings",
    "followups", "automation_runs", "outbox_events", "audit_events", "idempotency_records", "llm_usage",
    "mock_crm_contacts",
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = build_engine(get_settings().alembic_url)
    problems: list[str] = []
    cfg = Config("alembic.ini")
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        current = ctx.get_current_revision()
        if current != head:
            problems.append(f"révision courante {current!r} != head {head!r} (lancer `alembic upgrade head`)")
        diff = compare_metadata(ctx, Base.metadata)
        if diff:
            problems.append(f"dérive modèles/base : {diff[:3]}")
        tables = set(conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).scalars())
        missing_tables = REQUIRED_TABLES - tables
        if missing_tables:
            problems.append(f"tables manquantes : {sorted(missing_tables)}")
        names = set(conn.execute(text("SELECT conname FROM pg_constraint")).scalars())
        for name, why in REQUIRED_CONSTRAINTS.items():
            if name not in names:
                problems.append(f"contrainte absente {name} ({why})")
    if problems:
        print("[verify_schema] ÉCHEC")
        for p in problems:
            print(" -", p)
        return 1
    print(f"[verify_schema] OK — révision {head}, {len(REQUIRED_TABLES)} tables, {len(REQUIRED_CONSTRAINTS)} garde-fous présents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
