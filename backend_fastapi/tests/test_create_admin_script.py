from __future__ import annotations

import argparse

import pytest

from scripts import create_admin


def test_resolve_password_prefers_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(create_admin.ADMIN_BOOTSTRAP_PASSWORD_ENV, "env-secret-123")

    password = create_admin.resolve_password(
        argparse.Namespace(password="cli-secret-456")
    )

    assert password == "env-secret-123"


def test_resolve_password_uses_cli_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(create_admin.ADMIN_BOOTSTRAP_PASSWORD_ENV, raising=False)

    password = create_admin.resolve_password(
        argparse.Namespace(password="cli-secret-456")
    )

    assert password == "cli-secret-456"


def test_resolve_password_fails_in_non_interactive_mode_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(create_admin.ADMIN_BOOTSTRAP_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(create_admin.sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit, match="ADMIN_BOOTSTRAP_PASSWORD or --password"):
        create_admin.resolve_password(argparse.Namespace(password=None))
