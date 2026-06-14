"""Allow document delete while retaining audit history."""

from __future__ import annotations

from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "audit_event_document_id_fkey",
        "audit_event",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audit_event_document_id_fkey",
        "audit_event",
        "documents_document",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "audit_event_document_id_fkey",
        "audit_event",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audit_event_document_id_fkey",
        "audit_event",
        "documents_document",
        ["document_id"],
        ["id"],
    )
