"""Add transcription recording sessions and audio sections."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcription_recording_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consolidated_transcript", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["users_user.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents_document.id"]),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters_encounter.id"]),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_transcription_recording_session_session_id",
        "transcription_recording_session",
        ["session_id"],
        unique=True,
    )

    op.create_table(
        "transcription_audio_section",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.String(length=64), nullable=False),
        sa.Column("recording_session_id", sa.Integer(), nullable=False),
        sa.Column("client_section_id", sa.String(length=64), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("start_time_ms", sa.Integer(), nullable=False),
        sa.Column("end_time_ms", sa.Integer(), nullable=False),
        sa.Column("overlap_ms", sa.Integer(), nullable=False),
        sa.Column("gcs_object_name", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("raw_transcript", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recording_session_id"],
            ["transcription_recording_session.id"],
        ),
        sa.UniqueConstraint(
            "recording_session_id",
            "client_section_id",
            name="uq_transcription_section_client_id",
        ),
        sa.UniqueConstraint(
            "recording_session_id",
            "section_index",
            name="uq_transcription_section_index",
        ),
    )
    op.create_index(
        "ix_transcription_audio_section_section_id",
        "transcription_audio_section",
        ["section_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transcription_audio_section_section_id",
        table_name="transcription_audio_section",
    )
    op.drop_table("transcription_audio_section")
    op.drop_index(
        "ix_transcription_recording_session_session_id",
        table_name="transcription_recording_session",
    )
    op.drop_table("transcription_recording_session")
