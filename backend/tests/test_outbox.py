"""Outbox : claim atomique, lease, reprise après crash, backoff, dead-letter, rejeu (T15, T16)."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.database.session import get_sessionmaker
from app.models import AutomationRun, Lead, OutboxEvent
from app.services import outbox
from tests.conftest import service_headers, submit


def claim(client, limit=10, worker="t"):
    r = client.post("/api/v1/internal/outbox/claim", json={"limit": limit, "worker": worker}, headers=service_headers())
    assert r.status_code == 200, r.text
    return r.json()["events"]


def post(client, path, body, key=None):
    return client.post(f"/api/v1/internal/{path}", json=body, headers=service_headers(key or str(uuid.uuid4())))


def test_claim_reserves_event_and_creates_run(client, db):
    submit(client)
    events = claim(client)
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "LEAD_SUBMITTED" and e["attempt"] == 1 and e["workflow"] == "LF-WF-01-Lead-Qualification"
    assert "message" not in str(e["payload"]) and "@" not in str(e)  # aucune PII dans l'événement
    row = db.get(OutboxEvent, uuid.UUID(e["event_id"]))
    assert row.status == "PROCESSING" and row.locked_until > datetime.now(UTC)
    run = db.scalar(select(AutomationRun).where(AutomationRun.outbox_event_id == row.id))
    assert run.status == "STARTED" and run.attempt_count == 1
    assert db.get(Lead, row.lead_id).status == "PROCESSING"


def test_second_claim_returns_nothing_while_lease_is_valid(client):
    submit(client)
    assert len(claim(client)) == 1
    assert claim(client) == []


def test_concurrent_claims_never_return_same_event(client):
    for i in range(6):
        submit(client, email=f"user{i}@example.org")
    results: list[list[str]] = []
    barrier = threading.Barrier(4)

    def worker(n):
        barrier.wait()
        with get_sessionmaker()() as s:
            got = outbox.claim(s, limit=3, worker=f"w{n}")
            s.commit()
            results.append([str(c.event.id) for c in got])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    flat = [e for r in results for e in r]
    assert len(flat) == len(set(flat)) == 6  # tous réservés, aucun en double


def test_expired_lease_is_recovered_after_crash(client, db):
    submit(client)
    e = claim(client)[0]
    # le worker "plante" : on fait expirer la lease
    db.execute(update(OutboxEvent).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    again = claim(client)
    assert len(again) == 1 and again[0]["event_id"] == e["event_id"] and again[0]["attempt"] == 2
    stale = db.scalar(select(AutomationRun).where(AutomationRun.attempt_count == 1))
    db.refresh(stale)
    assert stale.status == "FAILED" and stale.error_code == "LEASE_EXPIRED"


def test_lease_expiry_exhausts_attempts_into_dead_letter_and_fails_lead(client, db):
    submit(client)
    for _ in range(3):  # OUTBOX_MAX_ATTEMPTS=3
        assert len(claim(client)) == 1
        db.execute(update(OutboxEvent).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()
    assert claim(client) == []
    ev = db.scalar(select(OutboxEvent))
    db.refresh(ev)
    assert ev.status == "DEAD_LETTER" and ev.last_error_code == "LEASE_EXPIRED"
    assert db.get(Lead, ev.lead_id).status == "FAILED"


def test_fail_retryable_schedules_backoff_then_becomes_due(client, db):
    submit(client)
    e = claim(client)[0]
    r = post(client, f"outbox/{e['event_id']}/fail",
             {"attempt": 1, "error_code": "LLM_UNAVAILABLE", "retryable": True, "message": "timeout"})
    assert r.status_code == 200 and r.json()["reason"] == "retrying"
    ev = db.get(OutboxEvent, uuid.UUID(e["event_id"]))
    assert ev.status == "RETRYING" and ev.next_attempt_at > datetime.now(UTC) + timedelta(seconds=20)
    assert claim(client) == []  # pas encore dû
    db.execute(update(OutboxEvent).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    retry = claim(client)
    assert len(retry) == 1 and retry[0]["attempt"] == 2
    run1 = db.scalar(select(AutomationRun).where(AutomationRun.attempt_count == 1))
    assert run1.status == "RETRYING" and run1.error_code == "LLM_UNAVAILABLE"


def test_backoff_grows_exponentially_and_is_capped(settings_override):
    from app.services.outbox import backoff_seconds

    settings_override(outbox_backoff_base_seconds="30", outbox_backoff_max_seconds="100")
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 100, 100]


def test_retry_after_is_respected(client, db):
    submit(client)
    e = claim(client)[0]
    r = post(client, f"outbox/{e['event_id']}/fail",
             {"attempt": 1, "error_code": "HTTP_429", "retryable": True, "retry_after_seconds": 600})
    assert r.json()["next_attempt_in_seconds"] >= 600


def test_non_retryable_failure_goes_straight_to_dead_letter(client, db):
    submit(client)
    e = claim(client)[0]
    r = post(client, f"outbox/{e['event_id']}/fail", {"attempt": 1, "error_code": "LLM_AUTH_ERROR", "retryable": False})
    assert r.json()["reason"] == "dead_letter"
    ev = db.get(OutboxEvent, uuid.UUID(e["event_id"]))
    assert ev.status == "DEAD_LETTER"
    assert db.get(Lead, ev.lead_id).status == "FAILED"


def test_max_attempts_leads_to_dead_letter(client, db):
    submit(client)
    for attempt in (1, 2, 3):
        e = claim(client)[0]
        assert e["attempt"] == attempt
        r = post(client, f"outbox/{e['event_id']}/fail", {"attempt": attempt, "error_code": "X", "retryable": True})
        db.execute(update(OutboxEvent).values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
                   .where(OutboxEvent.status == "RETRYING"))
        db.commit()
    assert r.json()["reason"] == "dead_letter"


def test_T15_complete_is_idempotent_and_replayed_callbacks_have_no_effect(client, db):
    submit(client)
    e = claim(client)[0]
    key = "same-callback-key"
    a = post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1}, key=key)
    b = post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1}, key=key)  # même clé : réponse mémorisée
    c = post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1})  # autre clé : déjà livré
    assert a.json() == {"applied": True, "reason": "applied"}
    assert b.json() == a.json() and b.headers["Idempotent-Replayed"] == "true"
    assert c.json() == {"applied": False, "reason": "already_delivered"}
    assert db.get(OutboxEvent, uuid.UUID(e["event_id"])).status == "DELIVERED"
    assert len(db.scalars(select(AutomationRun)).all()) == 1


def test_stale_attempt_callback_is_ignored(client, db):
    submit(client)
    e = claim(client)[0]
    db.execute(update(OutboxEvent).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    claim(client)  # tentative 2 réservée par un autre worker
    late = post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1})
    assert late.json() == {"applied": False, "reason": "stale_attempt"}
    assert db.get(OutboxEvent, uuid.UUID(e["event_id"])).status == "PROCESSING"


def test_same_key_with_different_body_is_409(client):
    submit(client)
    e = claim(client)[0]
    post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1}, key="k1")
    r = post(client, f"outbox/{e['event_id']}/complete", {"attempt": 1, "outcome": "MANUAL_REVIEW"}, key="k1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reuse"


def test_enqueue_dedupe_key_prevents_duplicate_events(db):
    from app.core.constants import EventType
    from app.services.seed import ensure_organization

    org = ensure_organization(db)
    a = outbox.enqueue(db, org_id=org.id, lead_id=None, event_type=EventType.LEAD_SUBMITTED, dedupe_key="dup")
    b = outbox.enqueue(db, org_id=org.id, lead_id=None, event_type=EventType.LEAD_SUBMITTED, dedupe_key="dup")
    db.commit()
    assert a.id == b.id
    assert len(db.scalars(select(OutboxEvent)).all()) == 1


def test_T16_failed_events_remain_visible_and_requeueable_by_admin_only(client, db):
    from tests.conftest import ADMIN, SALES, login

    submit(client)
    e = claim(client)[0]
    post(client, f"outbox/{e['event_id']}/fail", {"attempt": 1, "error_code": "N8N_DOWN", "retryable": False})
    run_id = str(db.scalar(select(AutomationRun.id)))

    sales_hdr = login(client, SALES)
    runs = client.get("/api/v1/automation-runs").json()["items"]
    assert runs[0]["event_status"] == "DEAD_LETTER" and runs[0]["can_retry"] is True
    assert client.post(f"/api/v1/automation-runs/{run_id}/retry", headers=sales_hdr).status_code == 403

    admin_hdr = login(client, ADMIN)
    r = client.post(f"/api/v1/automation-runs/{run_id}/retry", headers=admin_hdr)
    assert r.status_code == 202 and r.json()["status"] == "PENDING"
    again = claim(client)
    assert len(again) == 1 and again[0]["attempt"] == 2  # l'historique des tentatives est conservé
