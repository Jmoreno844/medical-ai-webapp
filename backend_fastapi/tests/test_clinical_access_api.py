from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.domains.auth.access import CLINICAL_ACCESS_DENIED_DETAIL
from app.domains.auth.service import get_current_user


def _doctor_without_clinical_access() -> SimpleNamespace:
    return SimpleNamespace(
        id=3,
        email="doctor@example.com",
        role="doctor",
        is_active=True,
        clinical_access_enabled=False,
        is_staff=False,
        is_superuser=False,
    )


def test_transcription_session_create_requires_clinical_access(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = _doctor_without_clinical_access
    try:
        response = TestClient(app).post(
            "/api/v1/transcription/sessions",
            json={"encounter_id": 1, "document_id": 2},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == CLINICAL_ACCESS_DENIED_DETAIL


def test_document_generate_requires_clinical_access(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = _doctor_without_clinical_access
    try:
        response = TestClient(app).post(
            "/api/v1/documents/generate",
            json={
                "context_document_id": 1,
                "transcription_document_id": 2,
                "new_document_id": 3,
                "doctor_template_id": 4,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == CLINICAL_ACCESS_DENIED_DETAIL
