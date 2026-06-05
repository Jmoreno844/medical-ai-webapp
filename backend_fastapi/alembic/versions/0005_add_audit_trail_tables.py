"""Add audit trail tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_user_session",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip_hmac", sa.String(length=64), nullable=False),
        sa.Column("network_prefix", sa.String(length=80), nullable=True),
        sa.Column("ip_encrypted", sa.Text(), nullable=True),
        sa.Column("user_agent_summary", sa.String(length=150), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users_user.id"]),
    )
    op.create_index(
        "ix_audit_user_session_organization_id",
        "audit_user_session",
        ["organization_id"],
    )
    op.create_index(
        "ix_audit_user_session_user_id",
        "audit_user_session",
        ["user_id"],
    )
    op.create_index(
        "ix_audit_user_session_ip_hmac",
        "audit_user_session",
        ["ip_hmac"],
    )
    op.create_index(
        "ix_audit_user_session_started_at",
        "audit_user_session",
        ["started_at"],
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_role_snapshot", sa.String(length=64), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("service_name", sa.String(length=128), nullable=True),
        sa.Column("service_account", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users_user.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["audit_user_session.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients_patient.id"]),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters_encounter.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents_document.id"]),
    )
    for index_name, columns in (
        ("ix_audit_event_created_at", ["created_at"]),
        ("ix_audit_event_organization_id", ["organization_id"]),
        ("ix_audit_event_actor_id", ["actor_id"]),
        ("ix_audit_event_action", ["action"]),
        ("ix_audit_event_result", ["result"]),
        ("ix_audit_event_session_id", ["session_id"]),
        ("ix_audit_event_patient_id", ["patient_id"]),
        ("ix_audit_event_encounter_id", ["encounter_id"]),
        ("ix_audit_event_document_id", ["document_id"]),
        ("ix_audit_event_trace_id", ["trace_id"]),
    ):
        op.create_index(index_name, "audit_event", columns)


def downgrade() -> None:
    for index_name in (
        "ix_audit_event_trace_id",
        "ix_audit_event_document_id",
        "ix_audit_event_encounter_id",
        "ix_audit_event_patient_id",
        "ix_audit_event_session_id",
        "ix_audit_event_result",
        "ix_audit_event_action",
        "ix_audit_event_actor_id",
        "ix_audit_event_organization_id",
        "ix_audit_event_created_at",
    ):
        op.drop_index(index_name, table_name="audit_event")
    op.drop_table("audit_event")

    for index_name in (
        "ix_audit_user_session_started_at",
        "ix_audit_user_session_ip_hmac",
        "ix_audit_user_session_user_id",
        "ix_audit_user_session_organization_id",
    ):
        op.drop_index(index_name, table_name="audit_user_session")
    op.drop_table("audit_user_session")
