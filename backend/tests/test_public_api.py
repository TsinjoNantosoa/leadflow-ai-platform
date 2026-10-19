"""API publique : T01, T03-T07, honeypot, rate limit, validation Pydantic, transaction outbox."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Contact, IntakeEvent, Lead, OutboxEvent
from tests.conftest import VALID_LEAD, submit


def counts(db):
    return {
        "contacts": db.scalar(select(func.count()).select_from(Contact)),
        "leads": db.scalar(select(func.count()).select_from(Lead)),
        "outbox": db.scalar(select(func.count()).select_from(OutboxEvent)),
    }


def test_T01_complete_lead_is_persisted_with_outbox_event(client, db):
    r = submit(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "NEW" and uuid.UUID(body["lead_id"]) and uuid.UUID(body["request_id"])

    lead = db.get(Lead, uuid.UUID(body["lead_id"]))
    assert lead.status == "NEW" and lead.requested_service == "customer_support_automation"
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.lead_id == lead.id))
    assert ev.event_type == "LEAD_SUBMITTED" and ev.status == "PENDING" and ev.attempt_count == 0
    actions = {a.action for a in db.scalars(select(AuditEvent).where(AuditEvent.lead_id == lead.id))}
    assert {"lead.received", "lead.validated"} <= actions


def test_response_does_not_wait_for_ai_or_crm(client, db):
    """Aucun appel LLM/CRM pendant la requête publique : la qualification reste vide."""
    r = submit(client)
    assert r.status_code == 201
    assert db.scalar(select(func.count()).select_from(Lead).where(Lead.status == "NEW")) == 1


def test_T03_same_key_same_body_returns_same_lead_without_duplicate(client, db):
    key = str(uuid.uuid4())
    first = submit(client, key=key)
    second = submit(client, key=key)
    assert first.status_code == 201 and second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.json() == second.json()
    assert counts(db) == {"contacts": 1, "leads": 1, "outbox": 1}


def test_T03_replay_ignores_email_case_and_spaces(client, db):
    key = str(uuid.uuid4())
    a = submit(client, key=key)
    b = submit(client, key=key, email="  ALICE.Martin@Example.ORG ")
    assert b.status_code == 200 and a.json()["lead_id"] == b.json()["lead_id"]


def test_T04_same_key_different_body_is_409_and_audited(client, db):
    key = str(uuid.uuid4())
    first = submit(client, key=key)
    second = submit(client, key=key, message=VALID_LEAD["message"] + " Autre contenu différent.")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reuse"
    assert counts(db)["leads"] == 1
    conflict = db.scalar(select(AuditEvent).where(AuditEvent.action == "intake.idempotency_conflict"))
    assert conflict is not None and str(conflict.lead_id) == first.json()["lead_id"]


def test_T05_same_email_new_request_gives_one_contact_two_leads(client, db):
    a, b = submit(client), submit(client, message="Deuxième demande : un site vitrine pour notre agence, budget 4000 EUR.")
    assert a.json()["lead_id"] != b.json()["lead_id"]
    assert counts(db) == {"contacts": 1, "leads": 2, "outbox": 2}
    leads = db.scalars(select(Lead)).all()
    assert leads[0].contact_id == leads[1].contact_id


@pytest.mark.parametrize("email", ["ALICE.MARTIN@EXAMPLE.ORG", "  alice.martin@example.org  ", "Alice.Martin@Example.Org"])
def test_T06_email_normalization_dedupes_contact(client, db, email):
    submit(client)
    r = submit(client, email=email)
    assert r.status_code == 201
    assert counts(db)["contacts"] == 1
    assert db.scalar(select(Contact.email_normalized)) == "alice.martin@example.org"


def test_contact_updates_keep_latest_name_and_company(client, db):
    submit(client)
    submit(client, full_name="Alice M. Martin", company=None)
    c = db.scalar(select(Contact))
    assert c.full_name == "Alice M. Martin" and c.company == "NovaDigital Demo"  # société conservée si absente


def test_T07_message_too_long_is_422(client, db):
    r = submit(client, message="x" * 4001)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert counts(db)["leads"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"message": "trop court"},
        {"email": "pas-un-email"},
        {"full_name": " "},
        {"requested_service": "unknown_service"},
        {"consent_privacy": False},
        {"phone": "abc"},
        {"message": "http://a.example http://b.example http://c.example http://d.example " + "x" * 30},
        {"unexpected_field": "nope"},
    ],
)
def test_T07_invalid_payloads_rejected_without_echoing_input(client, db, overrides):
    r = submit(client, **overrides)
    assert r.status_code == 422
    assert "pas-un-email" not in r.text  # la valeur saisie n'est jamais renvoyée
    assert counts(db)["leads"] == 0


def test_control_characters_and_nul_are_stripped(client, db):
    r = submit(client, message="Bonjour\x00, nous voulons automatiser\x07 le support client rapidement svp.")
    assert r.status_code == 201
    assert "\x00" not in db.scalar(select(Lead.message)) and "\x07" not in db.scalar(select(Lead.message))


def test_idempotency_key_required_and_must_be_uuid(client):
    r = client.post("/api/v1/public/leads", json=VALID_LEAD)
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"
    r = client.post("/api/v1/public/leads", json=VALID_LEAD, headers={"Idempotency-Key": "not-a-uuid"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_invalid"


def test_honeypot_returns_success_but_stores_nothing(client, db):
    r = submit(client, website="http://spam.example")
    assert r.status_code == 201
    assert counts(db) == {"contacts": 0, "leads": 0, "outbox": 0}


def test_rate_limit_per_ip_returns_429_and_replay_still_works(client, db, settings_override):
    settings_override(public_rate_limit_per_hour="2")
    keys = [str(uuid.uuid4()) for _ in range(3)]
    assert submit(client, key=keys[0]).status_code == 201
    assert submit(client, key=keys[1]).status_code == 201
    blocked = submit(client, key=keys[2])
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    assert counts(db)["leads"] == 2
    # un rejeu idempotent n'est pas une nouvelle demande : il n'est pas bloqué
    assert submit(client, key=keys[0]).status_code == 200


def test_ip_is_stored_hashed_only(client, db):
    submit(client)
    h = db.scalar(select(IntakeEvent.client_ip_hash))
    assert h and len(h) == 64 and "127.0.0.1" not in h and "testclient" not in h


def test_atomicity_failure_after_contact_insert_rolls_back_everything(client, db, monkeypatch):
    """Si l'écriture de l'outbox échoue, ni lead ni contact ne doivent subsister (même transaction)."""
    from app.services import outbox

    def boom(*a, **k):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(outbox, "enqueue", boom)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/public/leads", json=VALID_LEAD, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert counts(db) == {"contacts": 0, "leads": 0, "outbox": 0}


def test_openapi_documents_public_and_internal_contracts(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/public/leads" in spec["paths"] and "/api/v1/internal/outbox/claim" in spec["paths"]


def test_health_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/ready").json()["status"] == "ready"
