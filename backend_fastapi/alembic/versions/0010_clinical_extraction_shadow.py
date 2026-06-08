"""Add clinical extraction shadow tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_extraction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=64),
            nullable=False,
            server_default="clinical_facts_v1",
        ),
        sa.Column("extraction_model", sa.String(length=128), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "raw_model_output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "grounding_stats_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents_document.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["users_user.id"]),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters_encounter.id"]),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["transcription_recording_session.session_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_clinical_extraction_session_id",
        "clinical_extraction",
        ["session_id"],
    )
    op.create_table(
        "clinical_fact_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=False),
        sa.Column("fact_path", sa.String(length=512), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column(
            "supports_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("chunk_hint", sa.String(length=128), nullable=True),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column(
            "matched_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("uttered_by_role", sa.String(length=64), nullable=True),
        sa.Column("ambiguous", sa.Boolean(), nullable=False),
        sa.Column("speaker_mismatch", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["extraction_id"], ["clinical_extraction.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("clinical_fact_evidence")
    op.drop_index("ix_clinical_extraction_session_id", table_name="clinical_extraction")
    op.drop_table("clinical_extraction")
