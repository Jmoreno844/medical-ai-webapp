from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.domains.audit import api as audit_api
from app.domains.auth.service import get_current_user
from app.main import app


class FakeSession:
    async def commit(self) -> None:
        pass


def test_client_audit_event_rejects_unsupported_action() -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        role="doctor",
        name="Ada",
        last_name="Lovelace",
        is_staff=False,
        is_superuser=False,
    )
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/api/v1/audit/client-events",
            json={"action": "document.freeform", "document_id": 42},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported audit action"


def test_client_audit_event_accepts_allowlisted_action(monkeypatch) -> None:
    recorded: list[tuple[str, str]] = []

    async def fake_record_audit_event(*_args, **kwargs):
        recorded.append((kwargs["action"], kwargs["result"]))
        return None

    monkeypatch.setattr(audit_api, "record_audit_event", fake_record_audit_event)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        role="doctor",
        name="Ada",
        last_name="Lovelace",
        is_staff=False,
        is_superuser=False,
    )
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).post(
            "/api/v1/audit/client-events",
            json={"action": "document.copied", "document_id": 42},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert recorded == [("document.copied", "success")]
