"""Legacy no-op: revoked-token table is part of `0001` baseline DDL.

``fastapi_revoked_token`` is created in ``baseline_clinical_v1.sql`` applied
by ``0001``. This file remains so environments that have revision ``0002`` in
``alembic_version`` keep a linear history without re-running defunct DDL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25
"""

from __future__ import annotations

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
