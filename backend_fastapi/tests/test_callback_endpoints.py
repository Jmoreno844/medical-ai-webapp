from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.service_jwt import (
    issue_generation_callback_token,
    issue_transcription_callback_token,
)
from app.main import app


def test_generation_chunk_rejects_document_id_mismatch() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_generation_callback_token(
        user_id=7,
        document_id=42,
        process_id="gen_42_123",
        settings=settings,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).post(
            "/api/v1/documents/generation-chunk",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "document_id": 43,
                "process_id": "gen_42_123",
                "chunk": "hola",
                "is_complete": False,
                "is_error": False,
                "error": None,
            },
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid document ID"


def test_generation_chunk_rejects_process_id_mismatch() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_generation_callback_token(
        user_id=7,
        document_id=42,
        process_id="gen_42_123",
        settings=settings,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).post(
            "/api/v1/documents/generation-chunk",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "document_id": 42,
                "process_id": "gen_42_other",
                "chunk": "hola",
                "is_complete": False,
                "is_error": False,
                "error": None,
            },
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid processing ID"


def test_patch_by_function_rejects_path_document_id_mismatch() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_transcription_callback_token(
        user_id=7,
        document_id=42,
        settings=settings,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).patch(
            "/api/v1/documents/by-function/99",
            headers={"Authorization": f"Bearer {token}"},
            json={"content": "hola", "content_markdown": None, "content_json": None},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid document ID"


def test_transcription_notify_complete_rejects_payload_document_id_mismatch() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_transcription_callback_token(
        user_id=7,
        document_id=42,
        settings=settings,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).post(
            "/api/v1/transcription/notify-complete",
            headers={"Authorization": f"Bearer {token}"},
            json={"document_id": 99},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid document ID"
