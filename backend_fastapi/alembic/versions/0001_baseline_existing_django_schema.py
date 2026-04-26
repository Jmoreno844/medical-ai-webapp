"""Bootstrap the full clinical schema (Django-matched) plus FastAPI token table.

Revision ID: 0001
Revises:
Create Date: 2026-04-25

This revision applies the bundled PostgreSQL DDL in
`alembic/baseline/baseline_clinical_v1.sql` (see `alembic/baseline/execute_baseline.py`),
including auth/contenttypes tables used by the custom user model, application tables,
and `fastapi_revoked_token` (previously created in old revision ``0002``).

**Existing databases** that already applied the historical no-op ``0001`` and real
``0002`` should be **stamped** to the new head if you rebuild from this baseline;
do not re-run ``0001`` on a populated cluster.

**Regenerating** the SQL file: see `backend_fastapi/scripts/build_alembic_baseline_sql.py`
root and `docs/architecture/backend-fastapi-migration.md`.
"""

from __future__ import annotations

from app.db.alembic_baseline import run_baseline_upgrade

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_baseline_upgrade()


def downgrade() -> None:
    msg = "Downgrade of full baseline is not supported; restore from database backup."
    raise NotImplementedError(msg)
