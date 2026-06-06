"""Add clinical_access_enabled to users."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users_user",
        sa.Column(
            "clinical_access_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute("UPDATE users_user SET clinical_access_enabled = true")
    op.alter_column("users_user", "clinical_access_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("users_user", "clinical_access_enabled")
