from __future__ import annotations

import json

import pytest

from common.providers import ModelSpec
from common.llm_response import LlmResponse
from common.transcripts import TranscriptCase
from filtering.filter import run_filtering
from filtering.lib import (
    FilteringResult,
    audit_drop_turn_ids,
    enrich_filtering_result_for_export,
    expand_filtering_decisions,
    format_filtering_output_for_detail,
    load_filtering_prompt,
    parse_filtering_result,
    prompt_file_path,
    render_filtering_user_payload,
)


def test_parse_filtering_result() -> None:
    raw = json.dumps({"drop_turn_ids": [1, 2]})
    result = parse_filtering_result(raw)
    assert isinstance(result, FilteringResult)
    assert result.drop_turn_ids == [1, 2]


def test_parse_filtering_result_empty_means_all_keep() -> None:
    result = parse_filtering_result('{"drop_turn_ids": []}')
    assert result.drop_turn_ids == []


def test_prompt_file_path() -> None:
    path = prompt_file_path("v001")
    assert path.name == "filtering_v001.txt"
    assert path.is_file()


def test_load_filtering_prompt_v002_returns_py_system_prompt() -> None:
    from filtering.prompts.filtering_prompt_v001 import SYSTEM_PROMPT

    assert load_filtering_prompt("v002") == SYSTEM_PROMPT.strip()


def test_render_filtering_user_payload_v002_uses_transcript_block() -> None:
    case = TranscriptCase(
        id="tiny",
        transcript_json={
            "chunks": [
                {
                    "turns": [
                        {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
                    ]
                }
            ]
        },
    )
    payload = render_filtering_user_payload(case=case, prompt_version="v002")
    assert "<transcript>" in payload
    assert '"turns"' in payload


def test_expand_filtering_decisions_materializes_full_map() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "Buenos dias"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "Cansancio"},
        {"turn_id": 2, "speaker": "MEDICO", "text": "Entiendo"},
    ]
    result = FilteringResult(drop_turn_ids=[0, 2])
    expanded = expand_filtering_decisions(result, catalog)
    assert expanded["drop_turn_ids"] == [0, 2]
    assert expanded["keep_turn_ids"] == [1]
    assert expanded["drop_count"] == 2
    assert expanded["keep_count"] == 1
    assert expanded["decisions"][0]["keep"] == 0
    assert expanded["decisions"][1]["keep"] == 1


def test_enrich_filtering_result_for_export_includes_turn_text() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "Ok"},
    ]
    result = FilteringResult(drop_turn_ids=[0])
    exported = enrich_filtering_result_for_export(result, catalog)
    assert exported["decisions"][0]["text"] == "Hola"
    assert exported["decisions"][0]["keep"] == 0


def test_audit_drop_turn_ids_detects_extra_ids() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "ok"},
    ]
    result = FilteringResult(drop_turn_ids=[99])
    audit = audit_drop_turn_ids(result, catalog)
    assert audit.extra_turn_ids == [99]
    assert not audit.is_valid


def test_audit_drop_turn_ids_detects_duplicates() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "ok"},
    ]
    result = FilteringResult(drop_turn_ids=[0, 0])
    audit = audit_drop_turn_ids(result, catalog)
    assert audit.duplicate_turn_ids == [0]
    assert not audit.is_valid


def test_compact_output_detail_omits_raw_response() -> None:
    payload = {
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "filtering_result": {"drop_turn_ids": [], "keep_count": 2},
        "drop_audit": {"is_valid": True},
        "raw_response": "{\"drop_turn_ids\": []}",
    }
    compact = format_filtering_output_for_detail(payload, "compact")
    assert "raw_response" not in compact
    assert compact["filtering_result"]["keep_count"] == 2


def test_run_filtering_rejects_unknown_drop_turn_id() -> None:
    case = TranscriptCase(
        id="tiny",
        transcript_json={
            "chunks": [
                {
                    "turns": [
                        {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
                    ]
                }
            ]
        },
    )

    def fake_call_llm_detailed(**_kwargs: object) -> LlmResponse:
        return LlmResponse(content='{"drop_turn_ids": [99]}')

    import filtering.filter as filter_module

    original = filter_module.call_llm_detailed
    filter_module.call_llm_detailed = fake_call_llm_detailed
    try:
        with pytest.raises(ValueError, match="unknown_turn_id"):
            run_filtering(
                case=case,
                model_spec=ModelSpec(alias="openai", provider="openai", model="x"),
                system_prompt="test",
                prompt_version="v001",
            )
    finally:
        filter_module.call_llm_detailed = original


def test_run_filtering_rejects_duplicate_drop_turn_id() -> None:
    case = TranscriptCase(
        id="tiny",
        transcript_json={
            "chunks": [
                {
                    "turns": [
                        {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
                    ]
                }
            ]
        },
    )

    def fake_call_llm_detailed(**_kwargs: object) -> LlmResponse:
        return LlmResponse(content='{"drop_turn_ids": [0, 0]}')

    import filtering.filter as filter_module

    original = filter_module.call_llm_detailed
    filter_module.call_llm_detailed = fake_call_llm_detailed
    try:
        with pytest.raises(ValueError, match="duplicate_drop_turn_id"):
            run_filtering(
                case=case,
                model_spec=ModelSpec(alias="openai", provider="openai", model="x"),
                system_prompt="test",
                prompt_version="v001",
            )
    finally:
        filter_module.call_llm_detailed = original
