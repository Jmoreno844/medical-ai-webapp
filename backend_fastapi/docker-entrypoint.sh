#!/usr/bin/env sh
# Run Alembic before the ASGI server when deploying (Cloud Run / docker).
# Fails fast if DB URL or secrets are wrong; max-instances=1 avoids concurrent
# upgrade races in the first migration phase.
set -e
cd /app/backend_fastapi
if [ "${SKIP_ALEMBIC_ON_START:-}" = "1" ] || [ "${SKIP_ALEMBIC_ON_START:-}" = "true" ]; then
  exec "$@"
fi
alembic upgrade head
exec "$@"
