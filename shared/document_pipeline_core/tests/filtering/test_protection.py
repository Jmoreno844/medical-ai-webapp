from __future__ import annotations

import json

import pytest

from document_pipeline_core.common.transcripts import build_turn_catalog
from document_pipeline_core.filtering.filter import run_filtering
from document_pipeline_core.filtering.lib import (
    enrich_filtering_result_for_export,
    filtering_output_schema,
    parse_filtering_result,
)
from document_pipeline_core.filtering.prompts import filtering_prompt_v001
from document_pipeline_core.filtering.protection import (
    FULL_TRANSCRIPT_TURN_THRESHOLD,
    WINDOW_RADIUS,
    build_filtering_v002_payload,
    compute_turn_protection,
    is_admin_noise,
    is_pure_backchannel,
    is_short_answer,
    protection_reason_for_turn,
    sanitize_filtering_drop_turn_ids,
)
from document_pipeline_core.common.providers import ModelSpec


def _catalog(*turns: tuple[int, str, str]) -> list[dict[str, object]]:
    return [
        {"turn_id": turn_id, "speaker": speaker, "text": text}
        for turn_id, speaker, text in turns
    ]


def test_is_short_answer_rejects_empty_text() -> None:
    assert is_short_answer("") is False
    assert is_short_answer("   ") is False


def test_is_short_answer_accepts_brief_non_empty_text() -> None:
    assert is_short_answer("No.") is True
    assert is_short_answer("Dos semanas.") is True


def test_protect_doctor_clinical_questions() -> None:
    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "MEDICO", "¿Dónde le duele?"),
        (3, "MEDICO", "¿Medicamentos actuales?"),
    )
    protection = compute_turn_protection(catalog)
    assert protection.drop_eligible_turn_ids == []
    assert protection.protected_keep_reasons[1] == "doctor_clinical_question"


def test_protect_patient_concern_and_short_answers() -> None:
    catalog = _catalog(
        (1, "MEDICO", "¿Dolor en el pecho?"),
        (2, "PACIENTE", "No."),
        (3, "PACIENTE", "¿Cree que puede ser el corazón?"),
        (4, "PACIENTE", "Pensé que exageraba."),
        (5, "MEDICO", "¿Desde cuándo?"),
        (6, "PACIENTE", "Dos semanas."),
        (7, "PACIENTE", "A veces."),
    )
    protection = compute_turn_protection(catalog)
    assert 1 in protection.protected_keep_reasons
    assert protection.protected_keep_reasons[2] == "short_contextual_answer"
    assert protection.protected_keep_reasons[3] == "patient_clinical_question"
    assert protection.protected_keep_reasons[4] == "patient_concern_perception"
    assert protection.protected_keep_reasons[6] in {
        "short_contextual_answer",
        "clinical_signal",
    }
    assert protection.protected_keep_reasons[7] == "short_contextual_answer"


def test_protect_doctor_explanation_plan() -> None:
    catalog = _catalog(
        (1, "MEDICO", "Voy a examinarlo y pedir un ECG."),
        (2, "MEDICO", "Puede ser el corazón; haremos laboratorio."),
    )
    protection = compute_turn_protection(catalog)
    assert protection.drop_eligible_turn_ids == []
    assert protection.protected_keep_reasons[1] == "doctor_explanation_or_plan"
    assert protection.protected_keep_reasons[2] == "doctor_explanation_or_plan"


def test_admin_noise_and_pure_backchannel_are_eligible() -> None:
    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "PACIENTE", "No se escucha bien el audio."),
        (3, "PACIENTE", "mmm"),
        (4, "PACIENTE", "ok"),
    )
    protection = compute_turn_protection(catalog)
    assert 2 in protection.drop_eligible_turn_ids
    assert 3 in protection.drop_eligible_turn_ids
    assert 4 in protection.drop_eligible_turn_ids
    assert is_admin_noise("No se escucha bien el audio.")
    assert is_pure_backchannel("mmm")


def test_full_transcript_payload_includes_can_drop() -> None:
    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "PACIENTE", "mmm"),
    )
    protection = compute_turn_protection(catalog)
    payload, mode = build_filtering_v002_payload(catalog, protection)
    assert mode == "full_transcript"
    assert payload["drop_eligible_turn_ids"] == [2]
    turns = payload["turns"]
    assert turns[0]["can_drop"] is False
    assert turns[1]["can_drop"] is True


def test_windowed_payload_includes_neighbor_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "document_pipeline_core.filtering.protection.FULL_TRANSCRIPT_TURN_THRESHOLD",
        2,
    )
    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "PACIENTE", "mmm"),
        (3, "PACIENTE", "ok"),
    )
    protection = compute_turn_protection(catalog)
    payload, mode = build_filtering_v002_payload(catalog, protection)
    assert mode == "windowed_context"
    turn_ids = {int(turn["turn_id"]) for turn in payload["turns"]}
    assert 1 in turn_ids
    assert 2 in turn_ids
    assert 3 in turn_ids


def test_output_schema_only_lists_eligible_ids() -> None:
    schema = filtering_prompt_v001.output_schema(drop_eligible_turn_ids=[2, 5])
    items = schema["properties"]["drop_turn_ids"]["items"]
    assert items["enum"] == [2, 5]


def test_sanitize_removes_non_eligible_and_duplicates() -> None:
    sanitized = sanitize_filtering_drop_turn_ids(
        [2, 9, 2, 3],
        drop_eligible_turn_ids=[2, 3],
    )
    assert sanitized == [2, 3]


def test_no_eligible_short_circuit_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def _should_not_call(**kwargs: object) -> object:
        called["value"] = True
        raise AssertionError("call_llm_detailed should not run")

    monkeypatch.setattr(
        "document_pipeline_core.filtering.filter.call_llm_detailed",
        _should_not_call,
    )
    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "PACIENTE", "Dos semanas."),
    )
    transcript = {
        "session_id": "case",
        "chunks": [{"chunk_id": "s0", "turns": catalog}],
    }
    from document_pipeline_core.common.transcripts import TranscriptCase

    result, llm_response, diagnostics = run_filtering(
        case=TranscriptCase(id="case", transcript_json=transcript),
        model_spec=ModelSpec(alias="openai", provider="openai", model="gpt-5.4-mini"),
        system_prompt=filtering_prompt_v001.SYSTEM_PROMPT,
        prompt_version="v002",
    )
    assert called["value"] is False
    assert result.drop_turn_ids == []
    assert diagnostics is not None
    assert diagnostics.llm_skipped is True
    assert llm_response.request_params.get("filtering_llm_skipped") is True


def test_augment_filtering_decisions_with_protection_labels_each_bucket() -> None:
    from document_pipeline_core.filtering.lib import augment_filtering_decisions_with_protection

    catalog = _catalog(
        (1, "MEDICO", "¿Desde cuándo?"),
        (2, "PACIENTE", "mmm"),
        (3, "PACIENTE", "ok"),
    )
    protection = compute_turn_protection(catalog)
    decisions = [
        {"turn_id": 1, "keep": 1, "speaker": "MEDICO", "text": "¿Desde cuándo?"},
        {"turn_id": 2, "keep": 0, "speaker": "PACIENTE", "text": "mmm"},
        {"turn_id": 3, "keep": 1, "speaker": "PACIENTE", "text": "ok"},
    ]
    augmented, summary = augment_filtering_decisions_with_protection(
        decisions,
        drop_turn_ids=[2],
        protected_keep_reasons=protection.protected_keep_reasons,
        drop_eligible_turn_ids=protection.drop_eligible_turn_ids,
    )
    by_id = {int(row["turn_id"]): row for row in augmented}
    assert by_id[1]["disposition"] == "code_protected"
    assert by_id[2]["disposition"] == "model_dropped"
    assert by_id[3]["disposition"] == "model_kept"
    assert summary["model_kept_count"] == 1
    assert summary["model_dropped_count"] == 1


def test_enrich_filtering_export_includes_protection_metadata() -> None:
    from document_pipeline_core.filtering.lib import FilteringResult
    from document_pipeline_core.filtering.protection import FilteringRunDiagnostics

    catalog = _catalog((1, "MEDICO", "¿Desde cuándo?"), (2, "PACIENTE", "mmm"), (3, "PACIENTE", "ok"))
    protection = compute_turn_protection(catalog)
    diagnostics = FilteringRunDiagnostics.from_protection(
        protection,
        filtering_payload_mode="full_transcript",
    )
    export = enrich_filtering_result_for_export(
        FilteringResult(drop_turn_ids=[2]),
        catalog,
        diagnostics=diagnostics,
    )
    assert export["eligible_count"] == 2
    assert export["protected_count"] == 1
    assert export["model_kept_count"] == 1
    assert export["model_dropped_count"] == 1
    assert export["filtering_payload_mode"] == "full_transcript"
    assert isinstance(export["protected_turns"], list)
    assert export["protected_turns"][0]["reason"] == "doctor_clinical_question"
    assert export["decisions"][0]["disposition"] == "code_protected"


def test_protection_reason_none_for_isolated_greeting() -> None:
    catalog = _catalog((1, "MEDICO", "Hola"))
    assert protection_reason_for_turn(catalog, 0) is None


def test_window_constants_are_documented_defaults() -> None:
    assert FULL_TRANSCRIPT_TURN_THRESHOLD == 180
    assert WINDOW_RADIUS == 2


def test_parse_filtering_result_still_accepts_core_shape() -> None:
    parsed = parse_filtering_result('{"drop_turn_ids": [2]}')
    assert parsed.drop_turn_ids == [2]
