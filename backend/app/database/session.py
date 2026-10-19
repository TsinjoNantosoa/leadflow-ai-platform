from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(url: str | None = None) -> Engine:
    s = get_settings()
    return create_engine(
        url or s.database_url,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_recycle=s.db_pool_recycle_seconds,
        pool_timeout=s.db_pool_timeout_seconds,
        pool_pre_ping=True,  # Neon / Render : les connexions peuvent être fermées pendant la veille
        connect_args={
            "connect_timeout": s.db_connect_timeout_seconds,
            # Compatible PgBouncer en mode transaction (endpoint "pooled" de Neon).
            "prepare_threshold": None,
        },
    )


@lru_cache
def get_engine() -> Engine:
    return build_engine()


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête ; commit explicite côté services."""
    db = get_sessionmaker()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
