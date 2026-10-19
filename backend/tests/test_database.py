"""Schéma, contraintes SQL, migrations, seed, scripts d'exploitation."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Contact, Followup, Lead, Organization, Qualification
from tests.conftest import submit

BACKEND = Path(__file__).resolve().parents[1]


def _lead(db) -> Lead:
    org = db.scalar(select(Organization))
    c = Contact(organization_id=org.id, full_name="A B", email="a@example.org", email_normalized="a@example.org")
    db.add(c)
    db.flush()
    lead = Lead(organization_id=org.id, contact_id=c.id, message="m" * 30)
    db.add(lead)
    db.flush()
    return lead


def test_followup_cannot_be_sent_at_database_level(db):
    lead = _lead(db)
    for status in ("SENT", "READY_TO_SEND"):
        db.add(Followup(lead_id=lead.id, subject="s" * 5, body="b" * 30, status=status))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        lead = _lead(db)


def test_followup_sent_at_must_stay_null(db):
    from datetime import UTC, datetime

    lead = _lead(db)
    db.add(Followup(lead_id=lead.id, subject="sujet", body="b" * 30, status="APPROVED", sent_at=datetime.now(UTC)))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize("score,segment", [(80, "COLD"), (50, "HOT"), (10, "WARM"), (101, "HOT"), (-1, "COLD")])
def test_qualification_score_segment_constraints(db, score, segment):
    lead = _lead(db)
    db.add(Qualification(lead_id=lead.id, version=1, intent="other", score=score, segment=segment,
                         scoring_rule_version="scoring-v1"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_contact_email_must_be_canonical_and_unique_per_org(db):
    org = db.scalar(select(Organization))
    db.add(Contact(organization_id=org.id, full_name="X Y", email="X@Example.org", email_normalized="X@Example.org"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    org = db.scalar(select(Organization))
    db.add(Contact(organization_id=org.id, full_name="X Y", email="x@example.org", email_normalized="x@example.org"))
    db.flush()
    db.add(Contact(organization_id=org.id, full_name="X Z", email="x@example.org", email_normalized="x@example.org"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_lead_and_contact_must_belong_to_same_organization(db):
    org1 = db.scalar(select(Organization))
    org2 = Organization(name="Autre", slug="autre")
    db.add(org2)
    db.flush()
    c = Contact(organization_id=org1.id, full_name="A B", email="a@example.org", email_normalized="a@example.org")
    db.add(c)
    db.flush()
    db.add(Lead(organization_id=org2.id, contact_id=c.id, message="m" * 30))  # organisation différente du contact
    with pytest.raises(IntegrityError):
        db.flush()


def test_lead_status_check_constraint(db):
    lead = _lead(db)
    lead.status = "SENT"
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_contact_many_leads_is_allowed(client, db):
    for i in range(3):
        submit(client, message=f"Demande numéro {i} : nous voulons un site web pour notre société.")
    assert db.scalar(select(func.count()).select_from(Contact)) == 1
    assert db.scalar(select(func.count()).select_from(Lead)) == 3


def _run(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env_extra or {})}
    return subprocess.run([sys.executable, "-m", *args], cwd=BACKEND, capture_output=True, text=True, env=env, timeout=180)


def test_verify_schema_script_passes_on_migrated_database():
    r = _run("scripts.verify_schema")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_migrations_are_reversible_and_in_sync_with_models():
    """upgrade -> downgrade -> upgrade sur une base jetable, puis `alembic check` (aucune dérive)."""
    import os

    base = os.environ["DATABASE_URL"]
    scratch = "leadflow_migcheck_test"
    admin_url = base.rsplit("/", 1)[0] + "/postgres"
    from sqlalchemy import create_engine

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{scratch}"'))
        c.execute(text(f'CREATE DATABASE "{scratch}"'))
    url = base.rsplit("/", 1)[0] + f"/{scratch}"
    try:
        for cmd in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"], ["check"]):
            r = _run("alembic", "-x", f"db_url={url}", *cmd)
            assert r.returncode == 0, f"alembic {cmd}: {r.stdout}{r.stderr}"[-1500:]
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        admin.dispose()


def test_seed_is_rerunnable_and_marks_everything_as_demo(db):
    from app.services.seed import DEMO_LEADS, ensure_organization, ensure_users, seed_demo_data

    org = ensure_organization(db)
    first = seed_demo_data(db, org)
    db.commit()
    second = seed_demo_data(db, org)
    db.commit()
    assert first["leads"] == len(DEMO_LEADS) and second["leads"] == 0
    assert db.scalar(select(func.count()).select_from(Lead).where(Lead.is_demo.is_(False))) == 0
    assert db.scalar(select(func.count()).select_from(Contact).where(Contact.is_demo.is_(False))) == 0
    # couvre tous les cas demandés
    statuses = set(db.scalars(select(Lead.status)))
    assert {"READY", "MANUAL_REVIEW", "FAILED", "NEW"} <= statuses
    segs = set(db.scalars(select(Qualification.segment)))
    assert segs == {"HOT", "WARM", "COLD"}
    from app.models import CrmMapping

    assert {"SYNCED", "FAILED", "RETRYING"} <= set(db.scalars(select(CrmMapping.sync_status)))
    assert {"DRAFT", "APPROVED", "REJECTED"} == set(db.scalars(select(Followup.status)))
    assert ensure_users(db, org) == {"admin": None, "sales": None}  # comptes existants : rien n'est écrasé


def test_seed_does_not_overwrite_existing_data(db):
    from app.services.seed import DEMO_LEADS, ensure_organization, seed_demo_data

    org = ensure_organization(db)
    seed_demo_data(db, org)
    db.commit()
    target = db.scalar(select(Lead).where(Lead.message == DEMO_LEADS[0].message))
    target.status_reason = "MODIFIÉ PAR UN HUMAIN"
    db.commit()
    seed_demo_data(db, org)
    db.commit()
    db.refresh(target)
    assert target.status_reason == "MODIFIÉ PAR UN HUMAIN"


def test_seed_requires_explicit_passwords_in_production(db, settings_override):
    from app.services.seed import ensure_organization, ensure_users

    settings_override(app_env="production", session_secret="s" * 40, api_service_token="t" * 40,
                      demo_admin_password="", demo_sales_password="")
    org = ensure_organization(db)
    db.execute(text("DELETE FROM users"))
    with pytest.raises(RuntimeError, match="DEMO_ADMIN_PASSWORD"):
        ensure_users(db, org)


def test_demo_outbox_events_are_inert(db):
    from app.services import outbox
    from app.services.seed import ensure_organization, seed_demo_data

    org = ensure_organization(db)
    seed_demo_data(db, org)
    db.commit()
    assert outbox.claim(db, limit=50, worker="t") == []  # aucun événement de démo ne sera réservé par un vrai n8n


def test_retention_script_dry_run_then_apply(db):
    from datetime import UTC, datetime, timedelta

    from app.models import OutboxEvent

    org = db.scalar(select(Organization))
    old = datetime.now(UTC) - timedelta(days=90)
    db.add(OutboxEvent(organization_id=org.id, event_type="LEAD_SUBMITTED", dedupe_key="old", status="DELIVERED",
                       delivered_at=old))
    db.add(OutboxEvent(organization_id=org.id, event_type="LEAD_SUBMITTED", dedupe_key="recent", status="DELIVERED",
                       delivered_at=datetime.now(UTC)))
    db.add(OutboxEvent(organization_id=org.id, event_type="LEAD_SUBMITTED", dedupe_key="dead", status="DEAD_LETTER"))
    db.commit()
    dry = _run("scripts.purge_retention")
    assert dry.returncode == 0 and "simulation" in dry.stdout
    assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 3
    done = _run("scripts.purge_retention", "--apply")
    assert done.returncode == 0, done.stderr
    assert set(db.scalars(select(OutboxEvent.dedupe_key))) == {"recent", "dead"}  # jamais de purge des dead-letters


def test_contact_export_and_erasure_script(client, db):
    submit(client)
    exp = _run("scripts.contact_data", "export", "--email", "ALICE.martin@example.org")
    assert exp.returncode == 0, exp.stderr
    data = json.loads(exp.stdout)
    assert data["contact"][0]["email"] == "alice.martin@example.org" and len(data["leads"]) == 1
    sim = _run("scripts.contact_data", "delete", "--email", "alice.martin@example.org")
    assert "simulation" in sim.stdout and db.scalar(select(func.count()).select_from(Lead)) == 1
    done = _run("scripts.contact_data", "delete", "--email", "alice.martin@example.org", "--apply")
    assert done.returncode == 0, done.stderr
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Contact)) == 0 and db.scalar(select(func.count()).select_from(Lead)) == 0
    from app.models import AuditEvent

    trace = db.scalar(select(AuditEvent).where(AuditEvent.action == "privacy.contact_erased"))
    assert trace and "alice" not in json.dumps(trace.event_metadata)


def test_uuid_helper():
    assert uuid.UUID(str(uuid.uuid4()))
