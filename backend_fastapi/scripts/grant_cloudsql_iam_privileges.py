from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

import psycopg2
from psycopg2 import sql

POSTGRES_PASSWORD_ENV = "CLOUDSQL_POSTGRES_PASSWORD"


def ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def connect(*, dbname: str, user: str, password: str, host: str, port: str):
    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
    )


def grant_database_access(connection, *, database_name: str, iam_user: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(iam_user),
            )
        )
    connection.commit()


def grant_public_schema_access(
    connection,
    *,
    schema_name: str,
    iam_user: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema_name),
                sql.Identifier(iam_user),
            )
        )
    connection.commit()


async def main() -> int:
    ensure_project_root_on_path()

    host = require_env("DB_HOST")
    port = require_env("DB_PORT")
    postgres_password = require_env(POSTGRES_PASSWORD_ENV)

    backend_db_name = require_env("DB_NAME")
    backend_iam_user = require_env("DB_USER")
    copilot_db_name = require_env("COPILOT_AGENT_DB_NAME")
    copilot_iam_user = require_env("COPILOT_AGENT_DB_USER")

    admin_connection = connect(
        dbname="postgres",
        user="postgres",
        password=postgres_password,
        host=host,
        port=port,
    )
    admin_connection.autocommit = False
    try:
        grant_database_access(
            admin_connection,
            database_name=backend_db_name,
            iam_user=backend_iam_user,
        )
        grant_database_access(
            admin_connection,
            database_name=copilot_db_name,
            iam_user=copilot_iam_user,
        )
    finally:
        admin_connection.close()

    for database_name, iam_user in (
        (backend_db_name, backend_iam_user),
        (copilot_db_name, copilot_iam_user),
    ):
        scoped_connection = connect(
            dbname=database_name,
            user="postgres",
            password=postgres_password,
            host=host,
            port=port,
        )
        scoped_connection.autocommit = False
        try:
            grant_public_schema_access(
                scoped_connection,
                schema_name="public",
                iam_user=iam_user,
            )
        finally:
            scoped_connection.close()

    print(
        "Cloud SQL IAM privileges granted:",
        {
            "backend_db": backend_db_name,
            "backend_iam_user": backend_iam_user,
            "copilot_db": copilot_db_name,
            "copilot_iam_user": copilot_iam_user,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
