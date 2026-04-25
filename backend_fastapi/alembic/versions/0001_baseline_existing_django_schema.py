"""Baseline existing Django schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-25

This baseline intentionally performs no DDL. The current PostgreSQL schema is
owned by Django migrations until each domain is ported and verified.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")

