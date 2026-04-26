from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.domains.auth import api as auth_api
from app.main import app


class FakeSession:
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
        )

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

    assert response.status_code == 201
    assert response.json() == {
        "id": 42,
        "email": "doctor@example.com",
        "name": "Test",
        "last_name": "Doctor",
        "role": "doctor",
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
    response = TestClient(app).post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "correo existe" in response.json()["message"]
