from __future__ import annotations

import os
import time
import uuid

# --- Environnement de test : défini AVANT l'import de l'application ---------------------------------
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://leadflow:leadflow_local@localhost:5433/leadflow_test"
)
if not TEST_DB_URL.split("?")[0].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL doit désigner une base dont le nom finit par _test (garde-fou TRUNCATE)")

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DB_URL,
        "DATABASE_URL_DIRECT": "",
        "API_SERVICE_TOKEN": "test-service-token-0123456789abcdef-0123456789",
        "SESSION_SECRET": "test-session-secret-0123456789abcdef-0123456789",
        "LLM_PROVIDER": "mock",
        "CRM_PROVIDER": "mock",
        "OPENAI_API_KEY": "",
        "PUBLIC_RATE_LIMIT_PER_HOUR": "1000",
        "FRONTEND_URL": "http://localhost:5173",
        "ENABLE_REAL_EMAIL_SEND": "false",
        "OUTBOX_MAX_ATTEMPTS": "3",
        "OUTBOX_BACKOFF_BASE_SECONDS": "30",
        "OUTBOX_LEASE_SECONDS": "60",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.database.session import get_engine, get_sessionmaker  # noqa: E402
from app.integrations.llm.factory import set_llm_provider  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import ensure_organization, ensure_users  # noqa: E402

SERVICE_TOKEN = os.environ["API_SERVICE_TOKEN"]
ADMIN = ("admin@novadigital.example", "Admin-Test-Pass-1!")
SALES = ("sales@novadigital.example", "Sales-Test-Pass-1!")


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state(_migrated_database):
    """Base vide + organisation + 2 comptes avant CHAQUE test ; fournisseur LLM remis à zéro."""
    get_settings.cache_clear()
    set_llm_provider(None)
    with get_engine().begin() as conn:
        tables = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
        ).scalars().all()
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    with get_sessionmaker()() as db:
        org = ensure_organization(db)
        ensure_users(db, org, admin_password=ADMIN[1], sales_password=SALES[1])
        db.commit()
    yield
    get_settings.cache_clear()
    set_llm_provider(None)


@pytest.fixture
def settings_override(monkeypatch):
    def _set(**env: str):
        for k, v in env.items():
            monkeypatch.setenv(k.upper(), str(v))
        get_settings.cache_clear()
        set_llm_provider(None)

    return _set


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app, base_url="http://localhost") as c:
        yield c


def service_headers(key: str | None = None, **extra) -> dict[str, str]:
    h = {"Authorization": f"Bearer {SERVICE_TOKEN}", "X-LF-Timestamp": str(int(time.time() * 1000))}
    if key:
        h["Idempotency-Key"] = key
    h.update(extra)
    return h


@pytest.fixture
def svc():
    return service_headers


def login(client: TestClient, who: tuple[str, str] = SALES) -> dict[str, str]:
    """Ouvre une session et retourne les en-têtes CSRF à joindre aux mutations."""
    r = client.post("/api/v1/auth/login", json={"email": who[0], "password": who[1]})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.fixture
def sales(client):
    return login(client, SALES)


VALID_LEAD = {
    "full_name": "Alice Martin",
    "email": "alice.martin@example.org",
    "company": "NovaDigital Demo",
    "requested_service": "customer_support_automation",
    "message": "Bonjour, notre équipe veut automatiser le traitement des demandes clients. Budget indicatif 3000 EUR. Démarrage dans un mois.",
    "consent_privacy": True,
    "consent_marketing": False,
}


def submit(client: TestClient, body: dict | None = None, key: str | None = None, **overrides):
    payload = {**(body or VALID_LEAD), **overrides}
    return client.post("/api/v1/public/leads", json=payload, headers={"Idempotency-Key": key or str(uuid.uuid4())})


@pytest.fixture
def submit_lead(client):
    return lambda body=None, key=None, **kw: submit(client, body, key, **kw)


@pytest.fixture
def worker(client):
    from scripts.dev_worker import StandInWorker

    return StandInWorker(client, SERVICE_TOKEN)
