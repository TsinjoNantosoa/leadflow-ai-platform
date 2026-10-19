"""V1.1 : IP cliente derrière proxy, réveil n8n best-effort, création d'administrateur."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select

from app.api.v1.public import client_ip
from app.models import Lead, User
from app.services import wake
from tests.conftest import submit


class _Req:
    def __init__(self, xff: str | None, host: str = "10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = type("C", (), {"host": host})()


def test_xff_ignored_when_proxy_not_trusted(settings_override):
    settings_override(TRUST_PROXY_HEADERS="false")
    assert client_ip(_Req("1.2.3.4")) == "10.0.0.9"


def test_xff_spoofed_left_entries_are_ignored(settings_override):
    """Le client ajoute 6.6.6.6 à gauche ; le proxy de confiance ajoute l'IP réelle à droite."""
    settings_override(TRUST_PROXY_HEADERS="true", TRUSTED_PROXY_HOPS="1")
    assert client_ip(_Req("6.6.6.6, 203.0.113.7")) == "203.0.113.7"


def test_xff_two_hops_and_short_header_falls_back(settings_override):
    settings_override(TRUST_PROXY_HEADERS="true", TRUSTED_PROXY_HOPS="2")
    assert client_ip(_Req("6.6.6.6, 203.0.113.7, 76.76.21.1")) == "203.0.113.7"
    assert client_ip(_Req("203.0.113.7")) == "10.0.0.9"  # en-tête plus court que prévu : on ne devine pas


def test_wake_disabled_by_default(settings_override):
    settings_override(N8N_WAKE_WEBHOOK_URL="")
    assert wake.notify_n8n_wake() is False


def test_wake_sends_secret_header_and_no_business_data(settings_override, monkeypatch):
    settings_override(N8N_WAKE_WEBHOOK_URL="https://n8n.example.test/webhook/lf-wf-04-wake", N8N_WEBHOOK_SECRET="s3cret")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return httpx.Response(200)

    monkeypatch.setattr(wake.httpx, "post", fake_post)
    assert wake.notify_n8n_wake() is True
    assert seen["headers"]["X-LeadFlow-Webhook-Secret"] == "s3cret"
    assert seen["json"] == {"source": "leadflow-api"}


def test_scenario3_n8n_down_does_not_break_submission(client, db, settings_override, monkeypatch):
    """Scénario 3 : n8n injoignable → la soumission réussit, l'événement reste PENDING et réservable."""
    settings_override(N8N_WAKE_WEBHOOK_URL="https://n8n.example.test/webhook/lf-wf-04-wake")

    def boom(*a, **k):
        raise httpx.ConnectError("n8n down")

    monkeypatch.setattr(wake.httpx, "post", boom)
    r = submit(client)
    assert r.status_code == 201
    assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_wake_called_once_on_create_and_not_on_replay(client, settings_override, monkeypatch):
    settings_override(N8N_WAKE_WEBHOOK_URL="https://n8n.example.test/webhook/lf-wf-04-wake")
    calls = []
    monkeypatch.setattr(wake.httpx, "post", lambda *a, **k: calls.append(1) or httpx.Response(200))
    key = "11111111-1111-4111-8111-111111111111"
    assert submit(client, key=key).status_code == 201
    assert submit(client, key=key).status_code == 200
    assert len(calls) == 1


def test_create_admin_is_idempotent(db, monkeypatch):
    from scripts import create_admin

    monkeypatch.setenv("LF_ADMIN_EMAIL", "Boss@Example.org")
    monkeypatch.setenv("LF_ADMIN_PASSWORD", "a-long-enough-password")
    monkeypatch.setattr("sys.argv", ["create_admin"])
    assert create_admin.main() == 0
    assert create_admin.main() == 0
    db.expire_all()
    users = db.scalars(select(User).where(User.email_normalized == "boss@example.org")).all()
    assert len(users) == 1 and users[0].role == "ADMIN" and not users[0].is_demo


def test_create_admin_rejects_short_password(monkeypatch):
    from scripts import create_admin

    monkeypatch.setenv("LF_ADMIN_EMAIL", "boss@example.org")
    monkeypatch.setenv("LF_ADMIN_PASSWORD", "short")
    monkeypatch.setattr("sys.argv", ["create_admin"])
    assert create_admin.main() == 2


def test_openai_smoke_refuses_without_explicit_enable(monkeypatch):
    from scripts import openai_smoke

    monkeypatch.delenv("OPENAI_SMOKE_ENABLE", raising=False)
    monkeypatch.setattr("sys.argv", ["openai_smoke"])
    assert openai_smoke.main() == 3


def test_openai_smoke_requires_key_even_when_enabled(monkeypatch):
    from scripts import openai_smoke

    monkeypatch.setenv("OPENAI_SMOKE_ENABLE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["openai_smoke"])
    assert openai_smoke.main() == 2
