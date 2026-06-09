from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.domains.auth.service import get_current_user


def _clinical_doctor() -> SimpleNamespace:
    return SimpleNamespace(
        id=3,
        email="doctor@example.com",
        role="doctor",
        is_active=True,
        clinical_access_enabled=True,
        is_staff=False,
        is_superuser=False,
    )


def _local_settings() -> SimpleNamespace:
    return SimpleNamespace(
        environment="local",
        clinical_extraction_worker_base_url="http://localhost:8093",
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app.dependency_overrides[get_current_user] = _clinical_doctor
    app.dependency_overrides[get_settings] = _local_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_debug_clinical_extraction_requires_exactly_one_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/clinical-extraction/debug/extract",
        json={"language": "es"},
    )

    assert response.status_code == 422


def test_debug_clinical_extraction_hidden_outside_local_environment() -> None:
    app.dependency_overrides[get_current_user] = _clinical_doctor
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(environment="production")
    try:
        response = TestClient(app).post(
            "/api/v1/clinical-extraction/debug/extract",
            json={
                "transcript_json": {
                    "chunks": [
                        {
                            "chunk_id": "s0",
                            "turns": [{"speaker": "PACIENTE", "text": "Me duele."}],
                        }
                    ]
                }
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_debug_clinical_extraction_runs_worker_and_grounding(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_worker_call(
        *,
        settings,
        work_item,
        provider,
        model,
    ) -> dict:
        assert work_item["language"] == "es"
        assert len(work_item["chunks"]) == 1
        return {
            "success": True,
            "facts": {
                "mentions": [
                    {
                        "entity_type": "clinical_concept",
                        "entity_raw": "cabeza",
                        "proposition_raw": "Me duele la cabeza",
                        "speech_act": "assertion",
                        "subject_role": "patient",
                        "attributes": [],
                        "evidence": [
                            {
                                "quote": "Me duele la cabeza",
                                "turn_id": "s0:0",
                            }
                        ],
                    }
                ]
            },
            "extraction_model": "gemini-2.5-flash",
            "latency_ms": 321,
            "provider": "gemini",
        }

    monkeypatch.setattr(
        "app.domains.clinical_extraction.debug_controller.post_debug_clinical_extraction_to_worker",
        fake_worker_call,
    )

    response = client.post(
        "/api/v1/clinical-extraction/debug/extract",
        json={
            "transcript_json": {
                "language": "es",
                "chunks": [
                    {
                        "chunk_id": "s0",
                        "turns": [
                            {"speaker": "PACIENTE", "text": "Me duele la cabeza."}
                        ],
                    }
                ],
            },
            "context": {
                "encounter_id": 10,
                "document_id": 20,
                "doctor_id": 30,
                "patient_id": 40,
                "patient_name": "Paciente",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "extracted"
    assert payload["session_id"] == "debug"
    assert payload["processed_mentions"]["mentions"][0]["entity_raw"] == "la cabeza"
    assert payload["evidence"][0]["matched"] is True
    assert payload["grounding_stats"]["mentions_emitted"] == 1


def test_debug_clinical_extraction_loads_session_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording_session = SimpleNamespace(
        session_id="sess-1",
        encounter_id=10,
        document_id=20,
        doctor_id=30,
        status="consolidated",
        transcript_json={
            "chunks": [
                {
                    "chunk_id": "s0",
                    "turns": [{"speaker": "PACIENTE", "text": "Tengo fiebre."}],
                }
            ]
        },
        encounter=SimpleNamespace(
            occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            patient=SimpleNamespace(id=40, name="Paciente"),
        ),
    )

    async def fake_get_debug_transcript_session(db_session, *, session_id: str):
        assert session_id == "sess-1"
        return recording_session

    async def fake_worker_call(*, settings, work_item, provider, model) -> dict:
        assert work_item["session_id"] == "sess-1"
        return {
            "success": True,
            "facts": {"mentions": []},
            "extraction_model": "gemini-2.5-flash",
            "latency_ms": 100,
            "provider": "gemini",
        }

    monkeypatch.setattr(
        "app.domains.clinical_extraction.debug_controller.get_debug_transcript_session",
        fake_get_debug_transcript_session,
    )
    monkeypatch.setattr(
        "app.domains.clinical_extraction.debug_controller.post_debug_clinical_extraction_to_worker",
        fake_worker_call,
    )

    response = client.post(
        "/api/v1/clinical-extraction/debug/extract",
        json={"session_id": "sess-1"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-1"
