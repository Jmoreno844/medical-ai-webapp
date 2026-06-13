from __future__ import annotations

from pathlib import Path

import pytest

from common.json_utils import extract_json_object
from common.output_detail import normalize_output_detail
from common.prompts import normalize_prompt_version
from common.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_GEMINI_MODEL,
    _completion_limit_kwargs,
    _gemini_location,
    _is_groq_json_validate_error,
    default_model_for_provider,
    normalize_provider_name,
    parse_model_specs,
    provider_runtime_config,
)
from common.transcripts import (
    build_turn_catalog,
    enumerate_turn_ids,
    load_cases,
    select_cases,
)

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_INDEX = AI_PIPELINE_ROOT / "cases" / "index.json"


def test_load_cases_from_index_and_transcript_files() -> None:
    cases = load_cases(DEFAULT_CASES_INDEX)
    assert [case.id for case in cases] == [
        "case1",
        "case2",
        "case2_filtered",
        "medication_question_and_avoid",
        "eval_doc_clinica_co_001",
    ]
    assert cases[0].transcript_json["session_id"] == "case1"
    assert len(cases[4].transcript_json.get("chunks", [])) == 3


def test_select_cases_by_id() -> None:
    cases = load_cases(DEFAULT_CASES_INDEX)
    selected = select_cases(cases, case_id="medication_question_and_avoid")
    assert len(selected) == 1
    assert selected[0].id == "medication_question_and_avoid"


def test_enumerate_turn_ids() -> None:
    cases = load_cases(DEFAULT_CASES_INDEX)
    medication_case = next(
        case for case in cases if case.id == "medication_question_and_avoid"
    )
    turn_ids = enumerate_turn_ids(medication_case.transcript_json)
    assert turn_ids == [0, 1]
    catalog = build_turn_catalog(medication_case.transcript_json)
    assert catalog[0]["speaker"] == "PACIENTE"
    assert catalog[0]["turn_id"] == 0


def test_case1_has_explicit_turn_ids() -> None:
    cases = load_cases(DEFAULT_CASES_INDEX)
    case1 = next(case for case in cases if case.id == "case1")
    turns = case1.transcript_json["chunks"][0]["turns"]
    assert len(turns) == 125
    assert turns[0]["turn_id"] == 0
    assert turns[-1]["turn_id"] == 124
    catalog = build_turn_catalog(case1.transcript_json)
    assert [item["turn_id"] for item in catalog] == list(range(125))


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
    assert default_model_for_provider("gemini") == DEFAULT_GEMINI_MODEL
    assert default_model_for_provider("anthropic") == DEFAULT_ANTHROPIC_MODEL
    assert _gemini_location("gemini-3-flash-preview") == "global"
    assert _gemini_location("gemini-2.5-flash") == "us-east1"


def test_is_groq_json_validate_error() -> None:
    class FakeGroqError(Exception):
        body = {"error": {"code": "json_validate_failed"}}

    assert _is_groq_json_validate_error(FakeGroqError()) is True


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
