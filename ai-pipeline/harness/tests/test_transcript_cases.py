from __future__ import annotations

from document_pipeline_core.common.transcripts import (
    build_turn_catalog,
    enumerate_turn_ids,
    load_cases,
    select_cases,
)
from harness.paths import TRANSCRIPT_CASES_INDEX


def test_load_cases_from_index_and_transcript_files() -> None:
    cases = load_cases(TRANSCRIPT_CASES_INDEX)
    assert [case.id for case in cases] == [
        "case1",
        "case2",
        "case2_filtered",
        "case3",
        "medication_question_and_avoid",
        "eval_doc_clinica_co_001",
    ]
    assert cases[0].transcript_json["session_id"] == "case1"
    eval_case = next(case for case in cases if case.id == "eval_doc_clinica_co_001")
    assert len(eval_case.transcript_json.get("chunks", [])) == 3


def test_select_cases_by_id() -> None:
    cases = load_cases(TRANSCRIPT_CASES_INDEX)
    selected = select_cases(cases, case_id="medication_question_and_avoid")
    assert len(selected) == 1
    assert selected[0].id == "medication_question_and_avoid"


def test_enumerate_turn_ids() -> None:
    cases = load_cases(TRANSCRIPT_CASES_INDEX)
    medication_case = next(
        case for case in cases if case.id == "medication_question_and_avoid"
    )
    turn_ids = enumerate_turn_ids(medication_case.transcript_json)
    assert turn_ids == [0, 1]
    catalog = build_turn_catalog(medication_case.transcript_json)
    assert catalog[0]["speaker"] == "PACIENTE"
    assert catalog[0]["turn_id"] == 0


def test_case1_has_explicit_turn_ids() -> None:
    cases = load_cases(TRANSCRIPT_CASES_INDEX)
    case1 = next(case for case in cases if case.id == "case1")
    turns = case1.transcript_json["chunks"][0]["turns"]
    assert len(turns) == 125
    assert turns[0]["turn_id"] == 0
    assert turns[-1]["turn_id"] == 124
    catalog = build_turn_catalog(case1.transcript_json)
    assert [item["turn_id"] for item in catalog] == list(range(125))
