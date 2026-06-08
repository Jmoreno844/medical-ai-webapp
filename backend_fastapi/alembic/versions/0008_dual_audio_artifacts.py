"""Add original/clipped artifact columns for transcription audio sections."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcription_audio_section",
        sa.Column("original_gcs_object_name", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("original_content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("original_byte_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("clipped_gcs_object_name", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("clipped_content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("clipped_byte_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column(
            "transcription_source_gcs_object_name", sa.String(length=512), nullable=True
        ),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("frontend_vad_metadata_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcription_audio_section",
        sa.Column("transcription_source", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE transcription_audio_section
        SET
            original_gcs_object_name = gcs_object_name,
            original_content_type = content_type,
            original_byte_size = byte_size,
            clipped_gcs_object_name = gcs_object_name,
            clipped_content_type = content_type,
            clipped_byte_size = byte_size,
            transcription_source_gcs_object_name = gcs_object_name,
            transcription_source = 'legacy_single_blob'
        """
    )


def downgrade() -> None:
    op.drop_column("transcription_audio_section", "transcription_source")
    op.drop_column("transcription_audio_section", "frontend_vad_metadata_json")
    op.drop_column(
        "transcription_audio_section", "transcription_source_gcs_object_name"
    )
    op.drop_column("transcription_audio_section", "clipped_byte_size")
    op.drop_column("transcription_audio_section", "clipped_content_type")
    op.drop_column("transcription_audio_section", "clipped_gcs_object_name")
    op.drop_column("transcription_audio_section", "original_byte_size")
    op.drop_column("transcription_audio_section", "original_content_type")
    op.drop_column("transcription_audio_section", "original_gcs_object_name")
