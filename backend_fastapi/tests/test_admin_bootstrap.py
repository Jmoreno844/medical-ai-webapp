from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.security import make_django_password, verify_django_password
from app.domains.auth import admin_bootstrap
from app.domains.auth.roles import ADMIN_ROLE, DOCTOR_ROLE


class FakeSession:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user

    async def scalar(self, _statement):
        return self.existing_user

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_create_or_promote_admin_user_creates_new_admin(monkeypatch) -> None:
    created_user = SimpleNamespace(
        id=42,
        email="admin@example.com",
        password=make_django_password("testpass123"),
        name="Ada",
        last_name="Admin",
        role=DOCTOR_ROLE,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        last_login=None,
        date_joined=datetime.now(timezone.utc),
    )
    recorded_actions: list[str] = []

    async def fake_register_doctor_user(*_args, **_kwargs):
        return created_user

    async def fake_record_audit_event(_session, *, action: str, **_kwargs):
        recorded_actions.append(action)

    monkeypatch.setattr(admin_bootstrap, "register_doctor_user", fake_register_doctor_user)
    monkeypatch.setattr(admin_bootstrap, "record_audit_event", fake_record_audit_event)

    result = await admin_bootstrap.create_or_promote_admin_user(
        FakeSession(),
        email="admin@example.com",
        password="testpass123",
        name="Ada",
        last_name="Admin",
    )

    assert result.created is True
    assert result.promoted is True
    assert result.user.role == ADMIN_ROLE
    assert result.user.is_staff is True
    assert "user.created" in recorded_actions
    assert "user.role_changed" in recorded_actions


@pytest.mark.asyncio
async def test_create_or_promote_admin_user_promotes_existing_user(monkeypatch) -> None:
    existing_user = SimpleNamespace(
        id=7,
        email="doctor@example.com",
        password=make_django_password("oldpass123"),
        name="Doc",
        last_name="Tor",
        role=DOCTOR_ROLE,
        is_active=False,
        is_staff=False,
        is_superuser=False,
        last_login=None,
        date_joined=datetime.now(timezone.utc),
    )
    recorded_actions: list[str] = []

    async def fake_record_audit_event(_session, *, action: str, **_kwargs):
        recorded_actions.append(action)

    monkeypatch.setattr(admin_bootstrap, "record_audit_event", fake_record_audit_event)

    result = await admin_bootstrap.create_or_promote_admin_user(
        FakeSession(existing_user),
        email="doctor@example.com",
        password="newpass123",
        name="Doc",
        last_name="Torres",
        update_password=True,
        make_superuser=True,
    )

    assert result.created is False
    assert result.promoted is True
    assert result.reactivated is True
    assert result.password_updated is True
    assert result.user.role == ADMIN_ROLE
    assert result.user.is_staff is True
    assert result.user.is_superuser is True
    assert result.user.last_name == "Torres"
    assert verify_django_password("newpass123", result.user.password)
    assert "user.role_changed" in recorded_actions
    assert "user.activated" in recorded_actions
