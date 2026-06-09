from __future__ import annotations

import pytest

from app import providers
from app.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.schema import CLINICAL_MENTIONS_SCHEMA
from app.settings import Settings


def test_settings_defaults_to_gemini_flash() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="test")

    assert settings.provider_name == "gemini"
    assert settings.effective_model == "gemini-2.5-flash"


def test_settings_uses_openai_optional_model() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="openai",
    )

    assert settings.provider_name == "openai"
    assert settings.effective_model == "gpt-5.4-mini"


def test_settings_uses_anthropic_api_default_model() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="anthropic_api",
    )

    assert settings.provider_name == "anthropic_api"
    assert settings.effective_model == "claude-haiku-4-5-20251001"


def test_settings_maps_anthropic_alias() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="anthropic",
    )

    assert settings.provider_name == "anthropic_api"


def test_system_prompt_contains_v2_constraints() -> None:
    assert "ClinicalMentionsV2" in SYSTEM_PROMPT
    assert "No emitas metadatos como speaker o linguistic_polarity" in SYSTEM_PROMPT
    assert "Una mention = una sola proposición atómica" in SYSTEM_PROMPT
    assert "deferred_action" in SYSTEM_PROMPT
    assert "patient_preference" in SYSTEM_PROMPT


def test_prompt_includes_v2_name_and_chunks() -> None:
    prompt = build_extraction_prompt(
        {
            "session_id": "sess-1",
            "language": None,
            "chunks": [
                {
                    "chunk_id": "chunk-1:0",
                    "speaker": "patient",
                    "section_index": 0,
                    "text": "Me duele la cabeza.",
                }
            ],
        }
    )

    assert "Extrae ClinicalMentionsV2" in prompt
    assert "[chunk-1:0]" in prompt
    assert "speaker=patient" in prompt


def test_schema_is_strict_top_level() -> None:
    assert CLINICAL_MENTIONS_SCHEMA["additionalProperties"] is False
    assert CLINICAL_MENTIONS_SCHEMA["required"] == ["mentions"]


def test_mentions_schema_has_v2_fields() -> None:
    mention_properties = CLINICAL_MENTIONS_SCHEMA["properties"]["mentions"]["items"][
        "properties"
    ]

    assert set(mention_properties) == {
        "entity_type",
        "entity_raw",
        "proposition_raw",
        "speech_act",
        "subject_role",
        "attributes",
        "evidence",
    }


@pytest.mark.asyncio
async def test_extract_clinical_facts_uses_anthropic_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_create_structured_json_response(**kwargs):
        captured.update(kwargs)
        return {"mentions": []}

    monkeypatch.setattr(
        providers,
        "create_anthropic_structured_json_response",
        fake_create_structured_json_response,
    )

    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="anthropic_api",
        ANTHROPIC_API_KEY="test-key",
    )
    work_item = {"session_id": "sess-1", "chunks": []}

    result = await providers.extract_clinical_facts(
        work_item=work_item, settings=settings
    )

    assert result == {"mentions": []}
    assert captured["model"] == "claude-haiku-4-5-20251001"
    assert captured["api_key"] == "test-key"
    assert captured["schema"] == CLINICAL_MENTIONS_SCHEMA


@pytest.mark.asyncio
async def test_extract_clinical_facts_rejects_unknown_provider() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="unsupported",
    )

    with pytest.raises(ValueError):
        await providers.extract_clinical_facts(work_item={}, settings=settings)
