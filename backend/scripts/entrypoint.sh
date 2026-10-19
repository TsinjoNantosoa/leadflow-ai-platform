#!/bin/sh
# Point d'entrée du conteneur : migrations optionnelles puis serveur. Compatible Render (variable PORT).
set -e

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-server-header
