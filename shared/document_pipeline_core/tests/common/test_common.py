from __future__ import annotations

from document_pipeline_core.common.json_utils import extract_json_object
from document_pipeline_core.common.output_detail import normalize_output_detail
from document_pipeline_core.common.prompts import normalize_prompt_version
from document_pipeline_core.common.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_GEMINI_MODEL,
    GEMINI_MODEL_CHOICES,
    _completion_limit_kwargs,
    _gemini_location,
    _is_groq_json_validate_error,
    _raise_gemini_empty_response,
    default_model_for_provider,
    normalize_provider_name,
    parse_model_specs,
    provider_runtime_config,
)

import pytest


def test_extract_json_object_strips_markdown_fence() -> None:
    raw = '```json\n{"drop_turn_ids": [1]}\n```'
    assert extract_json_object(raw) == {"drop_turn_ids": [1]}


def test_extract_json_object_strips_thinking_blocks() -> None:
    raw = (
        "cluster 1: motivo consulta\n"
        '{"assignments": [{"cluster_id": "a", "section_ids": ["motivo_consulta"]}]}'
    )
    assert extract_json_object(raw) == {
        "assignments": [{"cluster_id": "a", "section_ids": ["motivo_consulta"]}]
    }


def test_extract_json_object_finds_json_after_preamble() -> None:
    raw = (
        "Analizo cluster por cluster...\n"
        '{"assignments": [{"cluster_id": "a", "section_ids": []}]}'
    )
    assert extract_json_object(raw) == {
        "assignments": [{"cluster_id": "a", "section_ids": []}]
    }


def test_extract_json_object_strips_redacted_thinking_tags() -> None:
    raw = (
        "cluster 1: motivo\n"
        '{"assignments": [{"cluster_id": "a", "section_ids": ["antecedentes"]}]}'
    )
    assert extract_json_object(raw) == {
        "assignments": [{"cluster_id": "a", "section_ids": ["antecedentes"]}]
    }


def test_parse_model_specs_rejects_disallowed_provider() -> None:
    with pytest.raises(ValueError, match="provider_not_allowed"):
        parse_model_specs("azure:gpt-4o")


def test_provider_runtime_config_uses_provider_specific_limit_param() -> None:
    openai_config = provider_runtime_config("openai")
    groq_config = provider_runtime_config("groq")
    gemini_config = provider_runtime_config("gemini")
    anthropic_config = provider_runtime_config("anthropic")
    assert "max_completion_tokens" in _completion_limit_kwargs(openai_config)
    assert "max_tokens" in _completion_limit_kwargs(groq_config)
    assert "max_output_tokens" in _completion_limit_kwargs(gemini_config)
    assert "max_tokens" in _completion_limit_kwargs(anthropic_config)
    assert "max_tokens" not in _completion_limit_kwargs(openai_config)


def test_default_models_and_provider_aliases() -> None:
    assert normalize_provider_name("google") == "gemini"
    assert normalize_provider_name("google_vertex") == "gemini"
    assert normalize_provider_name("google_genai") == "gemini"
    assert normalize_provider_name("anthropic_api") == "anthropic"
    assert normalize_provider_name("anthropic_vertex") == "anthropic"
    assert default_model_for_provider("google_vertex") == DEFAULT_GEMINI_MODEL
    assert default_model_for_provider("gemini") == DEFAULT_GEMINI_MODEL
    assert default_model_for_provider("anthropic") == DEFAULT_ANTHROPIC_MODEL
    assert GEMINI_MODEL_CHOICES == (
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
    )
    assert _gemini_location("gemini-2.5-flash") == "global"
    assert _gemini_location("gemini-3-flash-preview") == "global"
    assert _gemini_location("gemini-3.1-flash-lite") == "global"


def test_is_groq_json_validate_error() -> None:
    class FakeGroqError(Exception):
        body = {"error": {"code": "json_validate_failed"}}

    assert _is_groq_json_validate_error(FakeGroqError()) is True


def test_raise_gemini_empty_response_includes_finish_reason() -> None:
    from types import SimpleNamespace

    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))
        ],
        usage_metadata=SimpleNamespace(thoughts_token_count=15725),
    )
    with pytest.raises(ValueError, match="ai_pipeline_gemini_empty_response"):
        _raise_gemini_empty_response(response)
    with pytest.raises(ValueError, match="MAX_TOKENS"):
        _raise_gemini_empty_response(response)
    with pytest.raises(ValueError, match="15725"):
        _raise_gemini_empty_response(response)


def test_parse_model_specs_accepts_all_providers() -> None:
    specs = parse_model_specs(
        "openai:gpt-5.4-mini,groq:qwen/qwen3-32b,"
        "gemini:gemini-3-flash-preview,anthropic:claude-haiku-4-5-20251001"
    )
    assert [spec.provider for spec in specs] == [
        "openai",
        "groq",
        "gemini",
        "anthropic",
    ]


def test_normalize_prompt_version_and_output_detail() -> None:
    assert normalize_prompt_version("v001") == "v001"
    assert normalize_output_detail("compact") == "compact"
    with pytest.raises(ValueError, match="prompt_version_invalid"):
        normalize_prompt_version("bad")
