from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.models import AuditEvent
from app.db.session import get_db_session
from app.main import app
from app.domains.auth.service import get_current_user
from app.domains.documents import api as documents_api


class FakeSession:
    async def commit(self) -> None:
        pass


def _doctor_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        role="doctor",
        name="Doctor",
        last_name="User",
        is_staff=False,
        is_superuser=False,
    )


def test_audit_event_document_fk_uses_set_null_on_delete() -> None:
    foreign_key = next(
        constraint
        for constraint in AuditEvent.__table__.foreign_key_constraints
        if "document_id" in constraint.column_keys
    )

    assert foreign_key.ondelete == "SET NULL"


def test_delete_document_records_audit_before_delete(monkeypatch) -> None:
    document = SimpleNamespace(id=3, encounter_id=10)
    call_order: list[str] = []

    async def fake_get_document(*_args, **_kwargs):
        return document

    async def fake_record_audit_event(*_args, **kwargs):
        call_order.append(kwargs["action"])

    async def fake_delete_document_for_doctor(*_args, **_kwargs):
        call_order.append("delete_document_for_doctor")
        return True

    monkeypatch.setattr(documents_api, "get_document_for_doctor", fake_get_document)
    monkeypatch.setattr(documents_api, "record_audit_event", fake_record_audit_event)
    monkeypatch.setattr(
        documents_api,
        "delete_document_for_doctor",
        fake_delete_document_for_doctor,
    )

    app.dependency_overrides[get_current_user] = _doctor_user
    app.dependency_overrides[get_db_session] = lambda: FakeSession()
    try:
        response = TestClient(app).delete("/api/v1/documents/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert call_order == ["document.deleted", "delete_document_for_doctor"]
