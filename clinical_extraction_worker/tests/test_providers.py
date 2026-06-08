from __future__ import annotations

import pytest

from app import providers
from app.prompts import build_extraction_prompt
from app.schema import CLINICAL_FACTS_SCHEMA
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


def test_prompt_includes_chunk_ids_without_admin_metadata_request() -> None:
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

    assert "[chunk-1:0]" in prompt
    assert "Me duele la cabeza." in prompt


def test_schema_is_strict_top_level() -> None:
    assert CLINICAL_FACTS_SCHEMA["additionalProperties"] is False
    assert "chief_complaints" in CLINICAL_FACTS_SCHEMA["required"]


@pytest.mark.asyncio
async def test_extract_clinical_facts_rejects_unknown_provider() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        CLINICAL_EXTRACTION_PROVIDER="unsupported",
    )

    with pytest.raises(ValueError):
        await providers.extract_clinical_facts(work_item={}, settings=settings)
