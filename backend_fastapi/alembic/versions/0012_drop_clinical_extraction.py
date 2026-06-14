"""Drop clinical extraction shadow tables."""

from __future__ import annotations

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("clinical_fact_evidence")
    op.drop_table("clinical_extraction")


def downgrade() -> None:
    raise NotImplementedError("clinical_extraction tables are not restored")
