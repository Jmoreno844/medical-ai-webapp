"""Normalize user role values."""

from __future__ import annotations

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users_user
        SET role = CASE
            WHEN lower(trim(role)) IN ('medico', 'médico') THEN 'doctor'
            WHEN lower(trim(role)) = 'administrador' THEN 'admin'
            ELSE lower(trim(role))
        END
        WHERE role IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users_user
        SET role = CASE
            WHEN lower(trim(role)) = 'doctor' THEN 'medico'
            WHEN lower(trim(role)) = 'admin' THEN 'administrador'
            ELSE lower(trim(role))
        END
        WHERE role IS NOT NULL
        """
    )
