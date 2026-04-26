"""Load baseline PostgreSQL DDL from `alembic/baseline/baseline_clinical_v1.sql` for Alembic."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import sqlparse
from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

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


def run_baseline_upgrade() -> None:
    connection = op.get_bind()
    apply_clinical_baseline_ddl(connection)
