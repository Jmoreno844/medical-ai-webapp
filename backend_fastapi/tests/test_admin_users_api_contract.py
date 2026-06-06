from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.domains.admin_users import api as admin_users_api
from app.domains.auth.service import get_current_user
from app.main import app


class FakeSession:
    async def commit(self) -> None:
        pass


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        role="admin",
        name="Admin",
        last_name="User",
        is_staff=True,
        is_superuser=False,
    )


def test_internal_users_requires_admin() -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        role="doctor",
        name="Doctor",
        last_name="User",
        is_staff=False,
        is_superuser=False,
    )
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/api/v1/internal/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_internal_users_returns_list(monkeypatch) -> None:
    item = {
        "id": 7,
        "email": "doctor@example.com",
        "name": "Ada",
        "last_name": "Lovelace",
        "role": "doctor",
        "is_active": True,
        "clinical_access_enabled": True,
        "last_login": datetime.now(timezone.utc),
        "date_joined": datetime.now(timezone.utc),
        "active_session_count": 1,
        "last_session_started_at": datetime.now(timezone.utc),
        "login_success_24h": 2,
        "login_failure_24h": 0,
    }

    async def fake_list_admin_users(*_args, **_kwargs):
        return [item], 1

    monkeypatch.setattr(admin_users_api, "list_admin_users", fake_list_admin_users)
    app.dependency_overrides[get_current_user] = _admin_user
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/api/v1/internal/users?limit=10&offset=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["email"] == "doctor@example.com"


def test_internal_user_status_update_prevents_self_deactivate(monkeypatch) -> None:
    async def fake_get_admin_user_summary(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        admin_users_api,
        "get_admin_user_summary",
        fake_get_admin_user_summary,
    )

    class SessionWithUser(FakeSession):
        async def get(self, _model, _user_id: int):
            return SimpleNamespace(
                id=1,
                is_active=True,
                clinical_access_enabled=True,
            )

    app.dependency_overrides[get_current_user] = _admin_user
    app.dependency_overrides[get_db_session] = lambda: SessionWithUser()
    try:
        response = TestClient(app).patch(
            "/api/v1/internal/users/1/status",
            json={"is_active": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "No puedes desactivar tu propia cuenta"
