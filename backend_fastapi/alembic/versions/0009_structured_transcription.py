"""Add structured transcription JSON fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcription_audio_section",
        sa.Column("turns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "transcription_recording_session",
        sa.Column("transcript_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcription_recording_session", "transcript_json")
    op.drop_column("transcription_audio_section", "turns_json")
