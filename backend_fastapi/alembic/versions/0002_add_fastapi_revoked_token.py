"""Add FastAPI revoked token table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fastapi_revoked_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_fastapi_revoked_token_jti",
        "fastapi_revoked_token",
        ["jti"],
        unique=True,
    )
    op.create_index(
        "ix_fastapi_revoked_token_expires_at",
        "fastapi_revoked_token",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_fastapi_revoked_token_expires_at", table_name="fastapi_revoked_token")
    op.drop_index("ix_fastapi_revoked_token_jti", table_name="fastapi_revoked_token")
    op.drop_table("fastapi_revoked_token")
