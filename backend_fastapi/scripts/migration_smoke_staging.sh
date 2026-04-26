#!/usr/bin/env bash
# Apply Alembic as the only migration path for a fresh clinical schema
# (see `alembic/baseline/baseline_clinical_v1.sql`).
# Requires: PostgreSQL and env (DB_*, DATABASE_URL for FastAPI).
set -euo pipefail

# Repo root: .../github_medical_web_app (two levels up from this file)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "==> backend_fastapi: Alembic upgrade head (full clinical schema + FastAPI token table)"
(cd backend_fastapi && uv run alembic upgrade head)

echo "==> migration smoke: OK (run backend_fastapi pytest and app smoke next)"
