"""Store clinical mentions v2 evidence offsets."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clinical_fact_evidence",
        sa.Column("start_char", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clinical_fact_evidence",
        sa.Column("end_char", sa.Integer(), nullable=True),
    )
    op.alter_column(
        "clinical_extraction",
        "schema_version",
        server_default="clinical_mentions_v2",
        existing_type=sa.String(length=64),
    )


def downgrade() -> None:
    op.alter_column(
        "clinical_extraction",
        "schema_version",
        server_default="clinical_facts_v1",
        existing_type=sa.String(length=64),
    )
    op.drop_column("clinical_fact_evidence", "end_char")
    op.drop_column("clinical_fact_evidence", "start_char")
