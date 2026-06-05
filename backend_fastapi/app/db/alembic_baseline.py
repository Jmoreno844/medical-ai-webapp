"""Load baseline PostgreSQL DDL from `alembic/baseline/baseline_clinical_v1.sql` for Alembic."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import sqlparse
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.db.models import RevokedToken

_BASELINE = (
    Path(__file__).resolve().parents[2] / "alembic" / "baseline" / "baseline_clinical_v1.sql"
)


def _statement_body_is_empty(sql: str) -> bool:
    body_lines: list[str] = []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        body_lines.append(line)
    return not any(line.strip() for line in body_lines)


def _iter_baseline_statements() -> Iterator[str]:
    full = _BASELINE.read_text(encoding="utf-8")
    for raw in sqlparse.split(full):
        stmt = raw.strip()
        if not stmt or _statement_body_is_empty(stmt):
            continue
        if re.match(r"^--\s*PostgreSQL database dump", stmt):
            continue
        yield stmt


def apply_clinical_baseline_ddl(connection: Connection) -> None:
    if not _BASELINE.is_file():
        msg = f"Missing baseline SQL at {_BASELINE}"
        raise FileNotFoundError(msg)
    for statement in _iter_baseline_statements():
        connection.execute(text(statement))


def _has_existing_clinical_schema(connection: Connection) -> bool:
    inspector = inspect(connection)
    return inspector.has_table("auth_group") or inspector.has_table("users_user")


def _ensure_fastapi_revoked_token_table(connection: Connection) -> None:
    RevokedToken.__table__.create(bind=connection, checkfirst=True)


def run_baseline_upgrade() -> None:
    connection = op.get_bind()
    if _has_existing_clinical_schema(connection):
        # Staging/prod can point at a populated legacy schema. In that case we
        # treat the baseline as already satisfied and only backfill the FastAPI
        # token table if the historical cluster never created it.
        _ensure_fastapi_revoked_token_table(connection)
        return
    apply_clinical_baseline_ddl(connection)
