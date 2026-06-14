"""Seed the single clinical base template used by the document pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TEMPLATE_JSON_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "domains"
    / "documents"
    / "templates"
    / "consulta_estructurada_v001.json"
)


def _load_template_json() -> dict[str, object]:
    payload = json.loads(TEMPLATE_JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("consulta_estructurada_v001_json_must_be_object")
    return payload


def _markdown_from_template_json(data: dict[str, object]) -> str:
    lines: list[str] = []
    sections = data.get("sections")
    if not isinstance(sections, list):
        return ""
    for item in sections:
        if not isinstance(item, dict):
            continue
        heading = item.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            continue
        lines.append(f"## {heading.strip()}")
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            lines.append(description.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _base_template_seed() -> dict[str, str]:
    data = _load_template_json()
    name = data.get("name")
    document_kind = data.get("document_kind")
    return {
        "name": name.strip() if isinstance(name, str) and name.strip() else "Consulta estructurada",
        "document_kind": document_kind.strip()
        if isinstance(document_kind, str) and document_kind.strip()
        else "document",
        "content": _markdown_from_template_json(data),
    }


def upgrade() -> None:
    template = _base_template_seed()
    templates_table = sa.table(
        "templates_basetemplate",
        sa.column("name", sa.String),
        sa.column("document_kind", sa.String),
        sa.column("content", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    connection = op.get_bind()
    exists = connection.execute(
        sa.select(sa.literal(1)).where(
            sa.exists().where(
                sa.and_(
                    templates_table.c.name == template["name"],
                    templates_table.c.document_kind == template["document_kind"],
                )
            )
        )
    ).scalar_one_or_none()
    if exists:
        return

    connection.execute(
        templates_table.insert().values(
            name=template["name"],
            document_kind=template["document_kind"],
            content=template["content"],
            created_at=datetime.now(UTC),
        )
    )


def downgrade() -> None:
    template = _base_template_seed()
    templates_table = sa.table(
        "templates_basetemplate",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("document_kind", sa.String),
    )
    doctor_templates_table = sa.table(
        "templates_doctortemplate",
        sa.column("base_template_id", sa.Integer),
    )
    op.get_bind().execute(
        templates_table.delete().where(
            sa.and_(
                templates_table.c.name == template["name"],
                templates_table.c.document_kind == template["document_kind"],
                ~sa.exists().where(
                    doctor_templates_table.c.base_template_id == templates_table.c.id
                ),
            )
        )
    )
