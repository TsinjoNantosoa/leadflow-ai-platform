"""Prépare une base JETABLE pour les tests end-to-end Playwright : (re)création, migrations, comptes + données de démo.

    python -m scripts.e2e_prepare

Variables : E2E_DATABASE_URL (défaut : base `leadflow_playwright` du PostgreSQL de docker-compose),
E2E_ADMIN_PASSWORD / E2E_SALES_PASSWORD. Refuse toute base dont le nom ne se termine pas par `_playwright`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

URL = os.environ.get("E2E_DATABASE_URL", "postgresql+psycopg://leadflow:leadflow_local@localhost:5433/leadflow_playwright")
ADMIN_PW = os.environ.get("E2E_ADMIN_PASSWORD", "Admin-E2E-Pass-1!")
SALES_PW = os.environ.get("E2E_SALES_PASSWORD", "Sales-E2E-Pass-1!")


def main() -> None:
    url = make_url(URL)
    if not (url.database or "").endswith("_playwright"):
        sys.exit("E2E_DATABASE_URL doit désigner une base dont le nom finit par _playwright (garde-fou).")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    env = {
        **os.environ,
        "DATABASE_URL": URL,
        "DATABASE_URL_DIRECT": "",
        "DEMO_ADMIN_PASSWORD": ADMIN_PW,
        "DEMO_SALES_PASSWORD": SALES_PW,
        "SESSION_SECRET": "e2e-session-secret-0123456789abcdef0123456789",
        "PYTHONIOENCODING": "utf-8",
    }
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    subprocess.run([sys.executable, "-m", "scripts.seed_demo"], check=True, env=env)
    print("[e2e] base prête :", url.database)


if __name__ == "__main__":
    main()
