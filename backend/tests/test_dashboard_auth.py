"""Authentification, autorisations, CSRF, dashboard, revue humaine (T12, T13, T14)."""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Followup, Lead, OutboxEvent, User, UserSession
from tests.conftest import ADMIN, SALES, login, submit


def seed_pipeline(client, worker, n=1, **kw):
    ids = []
    for i in range(n):
        ids.append(submit(client, email=f"person{i}@example.org", full_name=f"Person {i}", **kw).json()["lead_id"])
    worker.drain()
    return ids


# --- T13 / T14 ------------------------------------------------------------------------------------
DASHBOARD_ENDPOINTS = [
    ("GET", "/api/v1/leads"),
    ("GET", f"/api/v1/leads/{uuid.uuid4()}"),
    ("GET", "/api/v1/metrics/overview"),
    ("GET", "/api/v1/automation-runs"),
    ("GET", "/api/v1/followups"),
    ("GET", "/api/v1/auth/me"),
    ("PATCH", f"/api/v1/followups/{uuid.uuid4()}"),
    ("POST", f"/api/v1/followups/{uuid.uuid4()}/approve"),
    ("POST", f"/api/v1/followups/{uuid.uuid4()}/reject"),
    ("POST", f"/api/v1/leads/{uuid.uuid4()}/retry"),
    ("POST", f"/api/v1/automation-runs/{uuid.uuid4()}/retry"),
]


@pytest.mark.parametrize("method,path", DASHBOARD_ENDPOINTS)
def test_T13_anonymous_cannot_reach_dashboard_and_no_pii_leaks(client, worker, method, path):
    seed_pipeline(client, worker)
    r = client.request(method, path, json={} if method != "GET" else None)
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"
    assert "example.org" not in r.text and "Alice" not in r.text


INTERNAL_ENDPOINTS = [
    ("POST", "/api/v1/internal/outbox/claim"),
    ("GET", f"/api/v1/internal/leads/{uuid.uuid4()}/payload"),
    ("GET", f"/api/v1/internal/leads/{uuid.uuid4()}/crm-context"),
    ("POST", f"/api/v1/internal/leads/{uuid.uuid4()}/qualification"),
]


@pytest.mark.parametrize("method,path", INTERNAL_ENDPOINTS)
def test_T14_wrong_or_missing_service_credentials_are_rejected(client, method, path):
    from tests.conftest import service_headers

    body = {"limit": 1}
    assert client.request(method, path, json=body).status_code == 401  # aucun credential
    bad = service_headers(str(uuid.uuid4()))
    bad["Authorization"] = "Bearer not-the-token"
    assert client.request(method, path, json=body, headers=bad).status_code == 401
    wrong_scheme = service_headers(str(uuid.uuid4()))
    wrong_scheme["Authorization"] = wrong_scheme["Authorization"].replace("Bearer ", "Basic ")
    assert client.request(method, path, json=body, headers=wrong_scheme).status_code == 401


def test_T14_no_processing_happens_with_bad_credentials(client, db):
    submit(client)
    r = client.post("/api/v1/internal/outbox/claim", json={"limit": 5}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert db.scalar(select(OutboxEvent.status)) == "PENDING"


def test_user_session_cookie_cannot_call_internal_api(client):
    login(client, ADMIN)
    r = client.post("/api/v1/internal/outbox/claim", json={"limit": 1})
    assert r.status_code == 401


def test_service_token_cannot_call_dashboard(client):
    from tests.conftest import service_headers

    assert client.get("/api/v1/leads", headers=service_headers()).status_code == 401


def test_replayed_internal_request_with_old_timestamp_is_rejected(client):
    from tests.conftest import service_headers

    h = service_headers()
    h["X-LF-Timestamp"] = str(int((time.time() - 3600) * 1000))
    r = client.post("/api/v1/internal/outbox/claim", json={"limit": 1}, headers=h)
    assert r.status_code == 401 and r.json()["error"]["code"] == "timestamp_stale"
    h2 = service_headers()
    del h2["X-LF-Timestamp"]
    assert client.post("/api/v1/internal/outbox/claim", json={"limit": 1}, headers=h2).json()["error"]["code"] == "timestamp_required"


def test_internal_api_is_fail_closed_without_configured_token(client, settings_override):
    settings_override(api_service_token="")
    from tests.conftest import service_headers

    r = client.post("/api/v1/internal/outbox/claim", json={"limit": 1}, headers=service_headers())
    assert r.status_code == 503


def test_mutations_require_idempotency_key(client):
    from tests.conftest import service_headers

    r = client.post(f"/api/v1/internal/outbox/{uuid.uuid4()}/complete", json={"attempt": 1}, headers=service_headers())
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"


# --- Login / session / CSRF -------------------------------------------------------------------------
def test_login_sets_httponly_cookie_and_returns_csrf(client):
    r = client.post("/api/v1/auth/login", json={"email": SALES[0], "password": SALES[1]})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "lf_session=" in cookie
    assert r.json()["user"]["role"] == "SALES" and "password" not in r.text.lower()
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == SALES[0]


def test_session_token_stored_only_as_hash(client, db):
    r = client.post("/api/v1/auth/login", json={"email": SALES[0], "password": SALES[1]})
    raw = client.cookies.get("lf_session")
    assert raw and db.scalar(select(func.count()).select_from(UserSession).where(UserSession.token_hash == raw)) == 0
    assert r.status_code == 200


def test_bad_credentials_generic_error_and_lockout(client, db, settings_override):
    settings_override(login_max_failures="3", login_lock_minutes="15")
    for _ in range(3):
        r = client.post("/api/v1/auth/login", json={"email": SALES[0], "password": "wrong"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.org", "password": "x"})
    assert unknown.json() == r.json()  # même réponse : pas d'énumération de comptes
    locked = client.post("/api/v1/auth/login", json={"email": SALES[0], "password": SALES[1]})
    assert locked.status_code == 401  # compte verrouillé même avec le bon mot de passe
    assert db.scalar(select(User.locked_until).where(User.email_normalized == SALES[0])) is not None


def test_login_email_is_case_insensitive(client):
    r = client.post("/api/v1/auth/login", json={"email": SALES[0].upper(), "password": SALES[1]})
    assert r.status_code == 200


def test_csrf_token_required_for_mutations(client, worker):
    seed_pipeline(client, worker)
    login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    assert client.post(f"/api/v1/followups/{fid}/approve").status_code == 403
    assert client.post(f"/api/v1/followups/{fid}/approve", headers={"X-CSRF-Token": "forged"}).json()["error"]["code"] == "csrf_invalid"


def test_foreign_origin_is_rejected_even_with_valid_csrf(client, worker):
    seed_pipeline(client, worker)
    hdr = login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    r = client.post(f"/api/v1/followups/{fid}/approve", headers={**hdr, "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "origin_not_allowed"
    ok = client.post(f"/api/v1/followups/{fid}/approve", headers={**hdr, "Origin": "http://localhost:5173"})
    assert ok.status_code == 200


def test_login_from_foreign_origin_rejected(client):
    r = client.post("/api/v1/auth/login", json={"email": SALES[0], "password": SALES[1]},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_logout_revokes_session(client):
    hdr = login(client, SALES)
    assert client.post("/api/v1/auth/logout", headers=hdr).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cors_allows_only_configured_origin(client):
    ok = client.options("/api/v1/leads", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert ok.headers.get("access-control-allow-credentials") == "true"
    bad = client.options("/api/v1/leads", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_security_headers_and_correlation_id(client):
    r = client.get("/health", headers={"X-Correlation-ID": "11111111-1111-4111-8111-111111111111"})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-correlation-id"] == "11111111-1111-4111-8111-111111111111"
    assert client.get("/health", headers={"X-Correlation-ID": "not-a-uuid"}).headers["x-correlation-id"] != "not-a-uuid"


# --- Dashboard ------------------------------------------------------------------------------------
def test_leads_list_filters_search_pagination_and_sort(client, worker):
    seed_pipeline(client, worker, n=3)
    submit(client, email="zoe@example.org", full_name="Zoé Dupont", company="Dupont SA", requested_service="other",
           message="Bonjour, je réfléchis à un projet digital sans cahier des charges, besoin de conseils généraux.")
    worker.drain()
    login(client, SALES)
    allr = client.get("/api/v1/leads").json()
    assert allr["total"] == 4 and allr["page"] == 1
    assert client.get("/api/v1/leads?page_size=2&page=2").json()["items"].__len__() == 2
    assert client.get("/api/v1/leads?q=dupont").json()["total"] == 1
    assert client.get("/api/v1/leads?q=%25").json()["total"] == 0  # caractères LIKE échappés
    hot = client.get("/api/v1/leads?segment=HOT").json()
    assert hot["total"] == 3 and all(i["segment"] == "HOT" for i in hot["items"])
    ordered = client.get("/api/v1/leads?sort=score&order=asc").json()["items"]
    scores = [i["score"] for i in ordered]
    assert scores == sorted(scores)
    assert client.get("/api/v1/leads?status=BOGUS").status_code == 422
    first = allr["items"][0]
    assert {"score", "segment", "crm_status", "followup_status", "status"} <= first.keys()


def test_lead_detail_contains_everything_the_page_needs(client, worker):
    lead_id = seed_pipeline(client, worker)[0]
    login(client, SALES)
    d = client.get(f"/api/v1/leads/{lead_id}").json()
    assert d["status"] == "READY" and d["contact"]["email"] == "person0@example.org"
    assert d["qualification"]["score"] > 0 and d["qualification"]["score_explanation"]["factors"]
    assert d["crm"]["sync_status"] == "SYNCED" and len(d["followups"]) == 1 and len(d["runs"]) == 3
    assert {a["action"] for a in d["audit"]} >= {"lead.received", "lead.qualified", "crm.synced", "draft.created"}
    steps = {s["key"]: s["state"] for s in d["timeline"]}
    assert steps == {"lead_received": "done", "validated": "done", "ai_qualification": "done", "scoring": "done",
                     "crm_sync": "done", "draft_generated": "done", "human_review": "attention", "decision": "pending"}


def test_timeline_reflects_reality_not_wishful_success(client, worker):
    lead_id = submit(client).json()["lead_id"]  # rien n'a encore tourné
    login(client, SALES)
    steps = {s["key"]: s["state"] for s in client.get(f"/api/v1/leads/{lead_id}").json()["timeline"]}
    assert steps["lead_received"] == "done" and steps["validated"] == "done"
    assert all(steps[k] == "pending" for k in ("ai_qualification", "scoring", "crm_sync", "draft_generated", "human_review", "decision"))


def test_timeline_manual_review_after_llm_failure(client, worker):
    lead_id = submit(client, message="Bonjour, nous voulons un site pour notre société. [[mock:invalid]]").json()["lead_id"]
    worker.drain()
    login(client, SALES)
    steps = {s["key"]: s for s in client.get(f"/api/v1/leads/{lead_id}").json()["timeline"]}
    assert steps["ai_qualification"]["state"] == "attention" and "LLM_INVALID_OUTPUT" in steps["ai_qualification"]["detail"]
    assert steps["scoring"]["state"] == "pending"


def test_unknown_lead_is_404(client):
    login(client, SALES)
    assert client.get(f"/api/v1/leads/{uuid.uuid4()}").status_code == 404


def test_metrics_are_computed_from_database(client, worker, db):
    seed_pipeline(client, worker, n=2)
    submit(client, message="Bonjour, nous voulons un site pour notre société. [[mock:invalid]]", email="x@example.org")
    worker.drain()
    submit(client, email="pending@example.org")  # reste NEW
    login(client, SALES)
    m = client.get("/api/v1/metrics/overview").json()
    assert m["leads"]["received"] == 4 and m["leads"]["qualified"] == 2 and m["leads"]["manual_review"] == 1
    assert m["leads"]["in_progress"] == 1
    assert m["segments"]["HOT"] == 2 and sum(m["segments"].values()) == 2
    assert m["drafts"] == {"DRAFT": 2}
    assert m["crm"] == {"SYNCED": 2}
    assert sum(p["count"] for p in m["series"]) == 4 and len(m["series"]) == 14
    assert m["data_origin"] == {"total_leads": 4, "demo_leads": 0, "real_leads": 4}
    assert m["qualification_latency_seconds"]["samples"] == 2
    assert m["runs_last_7_days"]["LF-WF-01-Lead-Qualification"]["SUCCEEDED"] == 2
    perf = m["automation_performance"]
    assert perf["successful_runs_7d"] >= 2 and perf["avg_duration_ms"] is not None
    assert perf["retries_total"] == 0 and perf["dead_letter"] == 0
    assert m["llm_usage"]["calls"] == 0  # les appels mock ne sont jamais comptés comme consommation réelle


def test_metrics_on_empty_database_do_not_invent_values(client):
    login(client, SALES)
    m = client.get("/api/v1/metrics/overview").json()
    assert m["leads"]["received"] == 0 and m["qualification_latency_seconds"]["p50"] is None
    assert m["llm_usage"]["estimated_cost_usd"] is None and m["recent_activity"] == []
    assert m["automation_performance"]["avg_duration_ms"] is None and m["automation_performance"]["retries_total"] == 0


def test_automation_runs_list_filters(client, worker):
    seed_pipeline(client, worker)
    login(client, SALES)
    allr = client.get("/api/v1/automation-runs").json()
    assert allr["total"] == 3 and {r["workflow_name"] for r in allr["items"]} == {
        "LF-WF-01-Lead-Qualification", "LF-WF-02-HubSpot-CRM-Sync", "LF-WF-03-Followup-Draft"}
    assert client.get("/api/v1/automation-runs?workflow=LF-WF-03-Followup-Draft").json()["total"] == 1
    assert client.get("/api/v1/automation-runs?status=FAILED").json()["total"] == 0
    r = allr["items"][0]
    assert uuid.UUID(r["correlation_id"]) and r["attempt_count"] == 1 and r["duration_ms"] is not None
    assert "secret" not in str(r).lower() and "token" not in str(r).lower()


# --- Revue humaine (T12) ---------------------------------------------------------------------------------
def test_T12_approve_sets_approved_audits_and_never_sends(client, worker, db):
    seed_pipeline(client, worker)
    hdr = login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    r = client.post(f"/api/v1/followups/{fid}/approve", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "APPROVED" and r.json()["approved_by"] == SALES[0]
    f = db.get(Followup, uuid.UUID(fid))
    assert f.status == "APPROVED" and f.sent_at is None
    assert db.scalar(select(func.count()).select_from(Followup).where(Followup.status.in_(["SENT", "READY_TO_SEND"]))) == 0
    a = db.scalar(select(AuditEvent).where(AuditEvent.action == "draft.approved"))
    assert a.actor_type == "user" and a.actor_ref == SALES[0] and a.event_metadata["sent"] is False
    # aucun nouvel événement outbox (donc rien à envoyer)
    assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "PENDING")) == 0
    again = client.post(f"/api/v1/followups/{fid}/approve", headers=hdr)  # double clic
    assert again.status_code == 200
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "draft.approved")) == 1


def test_approved_draft_cannot_be_edited_or_rejected(client, worker):
    seed_pipeline(client, worker)
    hdr = login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    client.post(f"/api/v1/followups/{fid}/approve", headers=hdr)
    assert client.patch(f"/api/v1/followups/{fid}", json={"subject": "Nouveau sujet"}, headers=hdr).status_code == 409
    assert client.post(f"/api/v1/followups/{fid}/reject", headers=hdr).status_code == 409


def test_edit_then_approve_with_optimistic_concurrency(client, worker, db):
    seed_pipeline(client, worker)
    hdr = login(client, SALES)
    item = client.get("/api/v1/followups").json()["items"][0]
    fid, v = item["id"], item["edit_version"]
    body = "Bonjour, merci pour votre message. Nous reviendrons vers vous après avoir étudié votre demande. Cordialement."
    r = client.patch(f"/api/v1/followups/{fid}", json={"body": body, "expected_version": v}, headers=hdr)
    assert r.status_code == 200 and r.json()["edit_version"] == v + 1 and r.json()["edited_by"] == SALES[0]
    stale = client.patch(f"/api/v1/followups/{fid}", json={"body": body + " bis", "expected_version": v}, headers=hdr)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "edit_conflict"
    assert client.post(f"/api/v1/followups/{fid}/approve", json={"expected_version": v}, headers=hdr).status_code == 409
    assert client.post(f"/api/v1/followups/{fid}/approve", json={"expected_version": v + 1}, headers=hdr).status_code == 200
    history = client.get(f"/api/v1/followups/{fid}/history").json()
    assert [h["action"] for h in history] == ["draft.approved", "draft.edited", "draft.created"]


def test_patch_validation(client, worker):
    seed_pipeline(client, worker)
    hdr = login(client, SALES)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    assert client.patch(f"/api/v1/followups/{fid}", json={}, headers=hdr).status_code == 422
    assert client.patch(f"/api/v1/followups/{fid}", json={"body": "court"}, headers=hdr).status_code == 422
    assert client.patch(f"/api/v1/followups/{fid}", json={"status": "SENT"}, headers=hdr).status_code == 422


def test_reject_records_reason_and_history(client, worker):
    seed_pipeline(client, worker)
    hdr = login(client, ADMIN)
    fid = client.get("/api/v1/followups").json()["items"][0]["id"]
    r = client.post(f"/api/v1/followups/{fid}/reject", json={"reason": "Ton trop familier"}, headers=hdr)
    assert r.json()["status"] == "REJECTED" and r.json()["reject_reason"] == "Ton trop familier"
    assert client.get("/api/v1/followups?status=DRAFT").json()["total"] == 0
    assert client.get("/api/v1/followups?status=REJECTED").json()["total"] == 1


def test_followup_of_unknown_id_is_404(client):
    hdr = login(client, SALES)
    assert client.post(f"/api/v1/followups/{uuid.uuid4()}/approve", headers=hdr).status_code == 404


def test_lead_retry_from_manual_review_creates_one_event(client, worker, db):
    lead_id = submit(client, message="Bonjour, nous voulons un site pour notre société. [[mock:invalid]]").json()["lead_id"]
    worker.drain()
    hdr = login(client, SALES)
    r = client.post(f"/api/v1/leads/{lead_id}/retry", headers=hdr)
    assert r.status_code == 202
    assert client.post(f"/api/v1/leads/{lead_id}/retry", headers=hdr).status_code == 409  # double clic
    assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "PENDING")) == 1
    assert db.get(Lead, uuid.UUID(lead_id)).status == "MANUAL_REVIEW"  # inchangé tant que non réservé


def test_lead_retry_requalifies_with_new_version(client, worker, db):
    lead_id = seed_pipeline(client, worker)[0]
    hdr = login(client, SALES)
    assert client.post(f"/api/v1/leads/{lead_id}/retry", headers=hdr).status_code == 202
    worker.drain()
    d = client.get(f"/api/v1/leads/{lead_id}").json()
    assert [q["version"] for q in d["qualification_history"]] == [2, 1]
    assert len(d["followups"]) == 1  # pas de second brouillon tant qu'un brouillon ouvert existe


def test_retry_unknown_or_archived_lead(client, db):
    hdr = login(client, SALES)
    assert client.post(f"/api/v1/leads/{uuid.uuid4()}/retry", headers=hdr).status_code == 404
    lead_id = submit(client).json()["lead_id"]
    lead = db.get(Lead, uuid.UUID(lead_id))
    lead.status = "ARCHIVED"
    db.commit()
    assert client.post(f"/api/v1/leads/{lead_id}/retry", headers=hdr).status_code == 409


def test_invalid_lead_transition_is_409_and_audited(db):
    from app.core.constants import LeadStatus
    from app.core.errors import ApiError
    from app.schemas.public import LeadCreate
    from app.services.intake import get_default_org, submit_lead
    from app.services.lead_state import transition
    from tests.conftest import VALID_LEAD

    org = get_default_org(db)
    receipt, _ = submit_lead(db, org=org, payload=LeadCreate(**VALID_LEAD), idempotency_key=uuid.uuid4(), client_ip_hash=None)
    lead = db.get(Lead, receipt.lead_id)
    with pytest.raises(ApiError) as e:
        transition(db, lead, LeadStatus.READY)  # NEW -> READY interdit
    assert e.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "lead.invalid_transition")) == 1
