"""Politique de rétention : purge les données techniques expirées (jamais les leads ni les contacts).

    python -m scripts.purge_retention            # simulation (aucune suppression)
    python -m scripts.purge_retention --apply    # suppression effective

Périmètre : événements outbox livrés, enregistrements d'idempotence, sessions expirées/révoquées.
Durées : RETENTION_OUTBOX_DAYS, RETENTION_IDEMPOTENCY_DAYS, RETENTION_SESSIONS_DAYS.
Les runs et événements d'audit sont conservés (traçabilité) : leur rétention doit être décidée avant un usage réel.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select

from app.core.config import get_settings
from app.database.session import get_sessionmaker
from app.models import IdempotencyRecord, OutboxEvent, UserSession


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    s = get_settings()
    now = datetime.now(UTC)
    targets = {
        "outbox_events (DELIVERED)": (
            OutboxEvent,
            and_(OutboxEvent.status == "DELIVERED", OutboxEvent.delivered_at < now - timedelta(days=s.retention_outbox_days),
                 OutboxEvent.is_demo.is_(False)),
        ),
        "idempotency_records": (
            IdempotencyRecord, IdempotencyRecord.created_at < now - timedelta(days=s.retention_idempotency_days)),
        "sessions": (
            UserSession,
            or_(UserSession.expires_at < now - timedelta(days=s.retention_sessions_days),
                UserSession.revoked_at < now - timedelta(days=s.retention_sessions_days)),
        ),
    }
    with get_sessionmaker()() as db:
        for label, (model, cond) in targets.items():
            n = db.execute(select(func.count()).select_from(model).where(cond)).scalar_one()
            if args.apply and n:
                db.execute(delete(model).where(cond))
            print(f"[retention] {label}: {n} ligne(s) {'supprimée(s)' if args.apply else 'à supprimer (simulation)'}")
        db.commit()


if __name__ == "__main__":
    main()
