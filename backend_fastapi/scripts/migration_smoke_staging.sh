#!/usr/bin/env bash
# Apply Alembic as the only migration path for a fresh clinical schema
# (see `alembic/baseline/baseline_clinical_v1.sql`).
# Optional: set USE_DJANGO_MIGRATE=1 to run `manage.py migrate` first
# (legacy rollback / comparison only).
# Requires: PostgreSQL and env (DB_*, DATABASE_URL for FastAPI).
set -euo pipefail

# Repo root: .../github_medical_web_app (two levels up from this file)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -n "${USE_DJANGO_MIGRATE:-}" ]]; then
  echo "==> USE_DJANGO_MIGRATE: legacy Django ORM migrate (not required for new installs)"
  (cd backend && uv run python manage.py migrate --noinput)
else
  echo "==> skipping Django migrate (set USE_DJANGO_MIGRATE=1 to enable)"
fi

echo "==> backend_fastapi: Alembic upgrade head (full clinical schema + FastAPI token table)"
(cd backend_fastapi && uv run alembic upgrade head)

echo "==> migration smoke: OK (run backend_fastapi pytest and app smoke next)"
