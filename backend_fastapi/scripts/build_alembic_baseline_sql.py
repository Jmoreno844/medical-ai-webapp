"""
Build `alembic/baseline/baseline_clinical_v1.sql` from pg_dump and fastapi.

Operator workflow when schema changes:
1. `manage.py migrate` a fresh database to current Django state.
2. `pg_dump --schema-only` the FastAPI table subset and `fastapi_revoked_token`.
3. Re-run this script, then refresh `0001` docstring and schema parity baselines.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# This file lives in backend_fastapi/scripts/
_BACKEND_FASTAPI_ROOT = Path(__file__).resolve().parents[1]
BASELINE_OUT = _BACKEND_FASTAPI_ROOT / "alembic" / "baseline" / "baseline_clinical_v1.sql"


def _fail(msg: str) -> NoReturn:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def _clean_pg_dump(s: str) -> str:
    s = re.sub(r"^\\restrict.*\n", "", s, flags=re.M)
    s = re.sub(r"^\\unrestrict.*\n", "", s, flags=re.M)
    idx = s.find("CREATE TABLE")
    if idx == -1:
        _fail("no CREATE TABLE in pg_dump output")
    return s[idx:].rstrip() + "\n"


def _pg_env() -> dict[str, str]:
    return {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "")}


def _run_pg_dump_django_baseline() -> str:
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5433")
    user = os.environ.get("PGUSER", "juan")
    ref_db = os.environ.get("ALEMBIC_REF_DJANGO_DB", "alembic_baseline_ref")
    env = _pg_env()
    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        ref_db,
        "--schema-only",
        "--no-owner",
        "--no-privileges",
    ]
    for t in (
        "django_content_type",
        "auth_group",
        "auth_group_permissions",
        "auth_permission",
        "users_user",
        "users_user_groups",
        "users_user_user_permissions",
        "patients_patient",
        "patients_patientdoctor",
        "encounters_encounter",
        "templates_basetemplate",
        "templates_doctortemplate",
        "templates_templateusage",
        "documents_document",
        "copilot_copilotrun",
        "copilot_copilotpatch",
        "copilot_copilotpatchset",
    ):
        cmd.extend(["-t", t])
    p = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        _fail(f"pg_dump django failed: {p.stderr}")
    return p.stdout


def _run_pg_dump_fastapi() -> str:
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = os.environ.get("PGPORT", "5433")
    user = os.environ.get("PGUSER", "juan")
    any_db = os.environ.get("ALEMBIC_REF_SOURCE_DB", "medical_web_app")
    env = _pg_env()
    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        any_db,
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "-t",
        "fastapi_revoked_token",
    ]
    p = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        _fail(f"pg_dump fastapi failed: {p.stderr}")
    return p.stdout


def main() -> None:
    django_sql = _run_pg_dump_django_baseline()
    fast_sql = _run_pg_dump_fastapi()
    out = _clean_pg_dump(django_sql) + "\n" + _clean_pg_dump(fast_sql) + "\n"
    BASELINE_OUT.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_OUT.write_text(out, encoding="utf-8")
    size = Path(BASELINE_OUT).stat().st_size
    print(
        f"Wrote {BASELINE_OUT} ({size} bytes) — verify DATABASE_URL/hosts before shipping."
    )


if __name__ == "__main__":
    main()
