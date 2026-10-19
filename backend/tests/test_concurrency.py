"""Concurrence réelle (threads + PostgreSQL) : idempotence, déduplication de contacts, double soumission."""

from __future__ import annotations

import threading
import uuid

from sqlalchemy import func, select

from app.database.session import get_sessionmaker
from app.models import Contact, Followup, IntakeEvent, Lead, OutboxEvent
from app.schemas.public import LeadCreate
from app.services.intake import get_default_org, submit_lead
from tests.conftest import VALID_LEAD


def run_parallel(n: int, fn):
    barrier = threading.Barrier(n)
    out: list = [None] * n

    def target(i):
        barrier.wait()
        try:
            out[i] = fn(i)
        except Exception as exc:  # noqa: BLE001
            out[i] = exc

    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return out


def intake(i: int, key: uuid.UUID, **over):
    with get_sessionmaker()() as s:
        org = get_default_org(s)
        return submit_lead(s, org=org, payload=LeadCreate(**{**VALID_LEAD, **over}), idempotency_key=key,
                           client_ip_hash=None)


def test_parallel_double_click_same_key_creates_exactly_one_lead(db):
    key = uuid.uuid4()
    results = run_parallel(8, lambda i: intake(i, key))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len({r[0].lead_id for r in results}) == 1
    assert sum(1 for r in results if r[1] is False) == 1  # un seul "premier", les autres sont des rejeux
    assert db.scalar(select(func.count()).select_from(Lead)) == 1
    assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    assert db.scalar(select(func.count()).select_from(IntakeEvent)) == 1


def test_parallel_same_email_different_keys_yields_one_contact(db):
    results = run_parallel(8, lambda i: intake(i, uuid.uuid4(), email="  ALICE.Martin@Example.org " if i % 2 else "alice.martin@example.org"))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert db.scalar(select(func.count()).select_from(Contact)) == 1
    assert db.scalar(select(func.count()).select_from(Lead)) == 8
    assert db.scalar(select(func.count(func.distinct(Lead.contact_id))).select_from(Lead)) == 1


def test_parallel_same_key_different_body_one_wins_others_conflict(db):
    from app.core.errors import ApiError

    key = uuid.uuid4()
    results = run_parallel(6, lambda i: intake(i, key, message=f"Message numéro {i} suffisamment long pour être valide ici."))
    ok = [r for r in results if isinstance(r, tuple)]
    conflicts = [r for r in results if isinstance(r, ApiError) and r.status_code == 409]
    assert len(ok) >= 1 and len(ok) + len(conflicts) == 6
    assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_parallel_followup_approval_is_applied_once(client, worker, db):
    from tests.conftest import SALES, login, submit

    submit(client)
    worker.drain()
    hdr = login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    from fastapi.testclient import TestClient

    from app.main import app

    def approve(i):
        with TestClient(app, base_url="http://localhost") as c:
            h = login(c, SALES)
            return c.post(f"/api/v1/followups/{fid}/approve", headers=h).status_code

    codes = run_parallel(5, approve)
    assert codes == [200] * 5
    from app.models import AuditEvent

    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "draft.approved")) == 1
    assert db.scalar(select(Followup.status)) == "APPROVED"
    assert hdr


def test_parallel_approve_and_reject_exactly_one_wins(client, worker, db):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import SALES, login, submit

    submit(client)
    worker.drain()
    login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]

    def act(i):
        with TestClient(app, base_url="http://localhost") as c:
            h = login(c, SALES)
            return c.post(f"/api/v1/followups/{fid}/{'approve' if i % 2 else 'reject'}", headers=h).status_code

    codes = run_parallel(6, act)
    assert 409 in codes and 200 in codes  # une décision l'emporte ; la décision contraire est refusée
    assert db.scalar(select(Followup.status)) in ("APPROVED", "REJECTED")
