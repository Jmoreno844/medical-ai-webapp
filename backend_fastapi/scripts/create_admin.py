from __future__ import annotations

import argparse
import asyncio
from getpass import getpass
import os
from pathlib import Path
import sys

ADMIN_BOOTSTRAP_PASSWORD_ENV = "ADMIN_BOOTSTRAP_PASSWORD"


def ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or promote an internal admin user for FastAPI.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--password")
    parser.add_argument(
        "--update-password",
        action="store_true",
        help="If the user already exists, replace the stored password too.",
    )
    parser.add_argument(
        "--superuser",
        action="store_true",
        help="Also set is_superuser=true for the target user.",
    )
    return parser.parse_args()


def resolve_password(args: argparse.Namespace) -> str:
    secret_password = os.environ.get(ADMIN_BOOTSTRAP_PASSWORD_ENV)
    if secret_password:
        return secret_password
    if args.password:
        return args.password
    if not sys.stdin.isatty():
        raise SystemExit(
            "Password is required in non-interactive mode. Use "
            f"{ADMIN_BOOTSTRAP_PASSWORD_ENV} or --password."
        )
    first = getpass("Password: ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    if not first:
        raise SystemExit("Password cannot be empty.")
    return first


async def main() -> int:
    ensure_project_root_on_path()
    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import AsyncSessionLocal
    from app.domains.auth.admin_bootstrap import create_or_promote_admin_user

    args = parse_args()

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(User.id).where(User.email == args.email.strip().lower())
        )
        password: str | None = None
        if existing is None or args.update_password:
            password = resolve_password(args)

        result = await create_or_promote_admin_user(
            session,
            email=args.email,
            password=password,
            name=args.name,
            last_name=args.last_name,
            make_superuser=args.superuser,
            update_password=args.update_password,
        )
        await session.commit()

    print(
        "Admin ready:",
        {
            "user_id": result.user.id,
            "email": result.user.email,
            "role": result.user.role,
            "is_staff": result.user.is_staff,
            "is_superuser": result.user.is_superuser,
            "created": result.created,
            "promoted": result.promoted,
            "reactivated": result.reactivated,
            "password_updated": result.password_updated,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
