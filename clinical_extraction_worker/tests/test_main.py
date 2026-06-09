from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ENVIRONMENT", "local")
    return TestClient(app)


def test_debug_clinical_extraction_endpoint_returns_facts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract_clinical_facts(
        *,
        work_item: dict,
        settings: Settings,
    ) -> dict:
        assert work_item["session_id"] == "debug-session"
        assert len(work_item["chunks"]) == 1
        return {
            "mentions": [
                {
                    "entity_type": "clinical_concept",
                    "entity_raw": "cefalea",
                    "proposition_raw": "cefalea",
                    "speech_act": "assertion",
                    "subject_role": "patient",
                    "attributes": [],
                    "evidence": [{"quote": "cefalea", "turn_id": "s0:0"}],
                }
            ]
        }

    monkeypatch.setattr(
        "app.main.extract_clinical_facts",
        fake_extract_clinical_facts,
    )

    response = client.post(
        "/api/v1/dev/clinical-extraction/extract",
        json={
            "session_id": "debug-session",
            "language": "es",
            "chunks": [
                {
                    "chunk_id": "s0:0",
                    "section_index": 0,
                    "speaker": "patient",
                    "text": "Me duele la cabeza.",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["facts"]["mentions"][0]["entity_raw"] == "cefalea"
    assert payload["provider"] == "gemini"


def test_debug_clinical_extraction_endpoint_accepts_anthropic_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract_clinical_facts(
        *,
        work_item: dict,
        settings: Settings,
    ) -> dict:
        assert settings.provider_name == "anthropic_api"
        assert settings.effective_model == "claude-haiku-4-5-20251001"
        return {"mentions": []}

    monkeypatch.setattr(
        "app.main.extract_clinical_facts",
        fake_extract_clinical_facts,
    )

    response = client.post(
        "/api/v1/dev/clinical-extraction/extract?provider=anthropic_api",
        json={"session_id": "debug-session", "chunks": []},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "anthropic_api"
    assert response.json()["extraction_model"] == "claude-haiku-4-5-20251001"


def test_debug_clinical_extraction_endpoint_returns_failure_without_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract_clinical_facts(
        *,
        work_item: dict,
        settings: Settings,
    ) -> dict:
        raise ValueError("clinical_extraction_response_invalid_json")

    monkeypatch.setattr(
        "app.main.extract_clinical_facts",
        fake_extract_clinical_facts,
    )

    response = client.post(
        "/api/v1/dev/clinical-extraction/extract",
        json={"session_id": "debug-session", "chunks": []},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["facts"] is None


def test_debug_clinical_extraction_endpoint_hidden_outside_local(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import settings as main_settings

    monkeypatch.setattr(
        "app.main.settings",
        main_settings.model_copy(update={"environment": "production"}),
    )

    response = client.post(
        "/api/v1/dev/clinical-extraction/extract",
        json={"session_id": "debug-session", "chunks": []},
    )

    assert response.status_code == 404
