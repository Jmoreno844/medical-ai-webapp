from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.domains.auth import api as auth_api
from app.main import app


class FakeSession:
    def add(self, _instance: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, _instance: object) -> None:
        pass


def test_register_contract_returns_created_user_profile(monkeypatch) -> None:
    async def fake_register_doctor_user(*_args, **_kwargs):
        return SimpleNamespace(
            id=42,
            email="doctor@example.com",
            name="Test",
            last_name="Doctor",
            role="doctor",
            is_active=True,
            clinical_access_enabled=False,
        )

    async def fake_create_audit_user_session(*_args, **_kwargs):
        return SimpleNamespace(id="audit-session-42")

    async def fake_record_audit_event(*_args, **_kwargs):
        return None

    async def fake_record_security_event(*_args, **_kwargs):
        return None

    def fake_issue_browser_tokens(*_args, **_kwargs) -> str:
        return "audit-session-42"

    monkeypatch.setattr(auth_api, "register_doctor_user", fake_register_doctor_user)
    monkeypatch.setattr(auth_api, "create_audit_user_session", fake_create_audit_user_session)
    monkeypatch.setattr(auth_api, "record_audit_event", fake_record_audit_event)
    monkeypatch.setattr(auth_api, "record_security_event", fake_record_security_event)
    monkeypatch.setattr(auth_api, "issue_browser_tokens", fake_issue_browser_tokens)
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/api/v1/auth/register",
            json={
                "email": "doctor@example.com",
                "password": "testpass123",
                "name": "Test",
                "last_name": "Doctor",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 201
    assert response.json() == {
        "success": True,
        "user": {
            "id": 42,
            "email": "doctor@example.com",
            "name": "Test",
            "last_name": "Doctor",
            "role": "doctor",
            "login_enabled": True,
            "clinical_access_enabled": False,
            "capabilities": {
                "can_access_admin_panel": False,
                "can_view_audit": False,
                "can_manage_users": False,
                "can_use_clinical_features": False,
            },
        },
    }


def test_register_contract_maps_duplicate_email_to_400(monkeypatch) -> None:
    async def fake_register_doctor_user(*_args, **_kwargs):
        raise ValueError("Email already registered")

    monkeypatch.setattr(auth_api, "register_doctor_user", fake_register_doctor_user)
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/api/v1/auth/register",
            json={
                "email": "doctor@example.com",
                "password": "testpass123",
                "name": "Test",
                "last_name": "Doctor",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"


def test_forgot_password_contract_is_generic() -> None:
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/api/v1/auth/forgot-password",
            json={"email": "unknown@example.com"},
        )
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "correo existe" in response.json()["message"]


def test_me_contract_includes_admin_capabilities() -> None:
    app.dependency_overrides[auth_api.get_current_user] = lambda: SimpleNamespace(
        id=9,
        email="admin@example.com",
        name="Ada",
        last_name="Admin",
        role="admin",
        is_active=True,
        clinical_access_enabled=True,
        is_staff=True,
        is_superuser=False,
    )
    try:
        response = TestClient(app).get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["capabilities"] == {
        "can_access_admin_panel": True,
        "can_view_audit": True,
        "can_manage_users": True,
        "can_use_clinical_features": True,
    }
    assert response.json()["login_enabled"] is True
    assert response.json()["clinical_access_enabled"] is True
