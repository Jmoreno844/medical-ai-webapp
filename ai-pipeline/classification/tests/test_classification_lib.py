from __future__ import annotations

import json

import pytest

from classification.classify import run_classification
from classification.lib import (
    DEFAULT_CASES_INDEX,
    ClassificationBatchResult,
    ClassificationResult,
    ClassificationSessionResult,
    ClusterAssignment,
    ClusterCase,
    audit_batch_assignments,
    audit_section_ids,
    audit_session_result,
    enrich_classification_result_for_export,
    enrich_classification_session_result_for_export,
    format_classification_output_for_detail,
    load_session_clusters,
    merge_batch_results,
    parse_classification_batch_result,
    parse_classification_result,
    prompt_file_path,
)
from classification.templates import load_template
from common.providers import ModelSpec


def test_load_template_finds_minimal_outpatient() -> None:
    template = load_template("minimal_outpatient_v001")
    assert template.id == "minimal_outpatient_v001"
    assert len(template.sections) == 6
    assert "motivo_consulta" in template.section_id_set()


def test_parse_classification_result() -> None:
    raw = json.dumps({"section_ids": ["enfermedad_actual", "motivo_consulta"]})
    result = parse_classification_result(raw)
    assert isinstance(result, ClassificationResult)
    assert result.section_ids == ["enfermedad_actual", "motivo_consulta"]


def test_parse_classification_result_empty_is_valid() -> None:
    result = parse_classification_result('{"section_ids": []}')
    assert result.section_ids == []


def test_prompt_file_path() -> None:
    path = prompt_file_path("v001")
    assert path.name == "classification_v001.txt"
    assert path.is_file()


def test_audit_section_ids_detects_unknown_ids() -> None:
    template = load_template("minimal_outpatient_v001")
    result = ClassificationResult(section_ids=["no_existe"])
    audit = audit_section_ids(result, template)
    assert audit.unknown_section_ids == ["no_existe"]
    assert not audit.is_valid


def test_audit_section_ids_detects_duplicates() -> None:
    template = load_template("minimal_outpatient_v001")
    result = ClassificationResult(section_ids=["motivo_consulta", "motivo_consulta"])
    audit = audit_section_ids(result, template)
    assert audit.duplicate_section_ids == ["motivo_consulta"]
    assert not audit.is_valid


def test_enrich_classification_result_for_export_returns_section_ids() -> None:
    template = load_template("minimal_outpatient_v001")
    result = ClassificationResult(section_ids=["motivo_consulta"])
    exported = enrich_classification_result_for_export(result, template)
    assert exported["section_ids"] == ["motivo_consulta"]
    assert exported["section_count"] == 1


def test_compact_output_detail_omits_raw_response() -> None:
    payload = {
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "classification_result": {"section_ids": ["motivo_consulta"]},
        "section_audit": {"is_valid": True},
        "raw_response": '{"section_ids": ["motivo_consulta"]}',
    }
    compact = format_classification_output_for_detail(payload, "compact")
    assert "raw_response" not in compact
    assert compact["classification_result"]["section_ids"] == ["motivo_consulta"]


def test_prompt_file_path_v002() -> None:
    path = prompt_file_path("v002")
    assert path.name == "classification_v002.txt"
    assert path.is_file()


def test_parse_classification_batch_result() -> None:
    raw = json.dumps(
        {
            "assignments": [
                {
                    "cluster_id": "case1_a",
                    "section_ids": ["motivo_consulta"],
                }
            ]
        }
    )
    result = parse_classification_batch_result(raw)
    assert len(result.assignments) == 1
    assert result.assignments[0].cluster_id == "case1_a"
    assert result.assignments[0].section_ids == ["motivo_consulta"]


def test_parse_classification_batch_result_ignores_extra_reasoning() -> None:
    raw = json.dumps(
        {
            "assignments": [
                {
                    "cluster_id": "case1_a",
                    "reasoning": "legacy field",
                    "section_ids": ["motivo_consulta"],
                }
            ]
        }
    )
    result = parse_classification_batch_result(raw)
    assert result.assignments[0].section_ids == ["motivo_consulta"]


def test_audit_batch_assignments_detects_missing_cluster() -> None:
    template = load_template("minimal_outpatient_v001")
    result = ClassificationBatchResult(
        assignments=[
            ClusterAssignment(
                cluster_id="case1_a",
                section_ids=["motivo_consulta"],
            )
        ]
    )
    audit = audit_batch_assignments(result, ["case1_a", "case1_b"], template)
    assert audit.missing_cluster_ids == ["case1_b"]
    assert not audit.is_valid


def test_merge_batch_results_combines_assignments() -> None:
    first = ClassificationBatchResult(
        assignments=[
            ClusterAssignment(cluster_id="a", section_ids=["motivo_consulta"])
        ]
    )
    second = ClassificationBatchResult(
        assignments=[
            ClusterAssignment(cluster_id="b", section_ids=["antecedentes"])
        ]
    )
    merged = merge_batch_results([first, second])
    assert [item.cluster_id for item in merged.assignments] == ["a", "b"]


def test_audit_session_result() -> None:
    template = load_template("minimal_outpatient_v001")
    session = ClassificationSessionResult(
        assignments=[
            ClusterAssignment(cluster_id="a", section_ids=["motivo_consulta"])
        ]
    )
    audit = audit_session_result(session, ["a"], template)
    assert audit.is_valid


def test_load_session_clusters_case1() -> None:
    clusters = load_session_clusters(DEFAULT_CASES_INDEX, "case1")
    assert len(clusters) == 12
    assert clusters[0].id.startswith("case1_")


def test_enrich_classification_session_result_for_export() -> None:
    template = load_template("minimal_outpatient_v001")
    session = ClassificationSessionResult(
        assignments=[
            ClusterAssignment(
                cluster_id="case1_a",
                section_ids=["motivo_consulta"],
            )
        ]
    )
    exported = enrich_classification_session_result_for_export(session, template)
    assert exported["assignment_count"] == 1
    assert exported["assignments"][0]["section_ids"] == ["motivo_consulta"]


def test_run_classification_rejects_unknown_section_id() -> None:
    cluster_case = ClusterCase(
        id="tiny",
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "test",
            "turns": [
                {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
            ],
        },
    )
    template = load_template("minimal_outpatient_v001")

    def fake_call_llm(**_kwargs: object) -> str:
        return '{"section_ids": ["seccion_inventada"]}'

    import classification.classify as classify_module

    original = classify_module.call_llm
    classify_module.call_llm = fake_call_llm
    try:
        with pytest.raises(ValueError, match="unknown_section_id"):
            run_classification(
                cluster_case=cluster_case,
                template=template,
                model_spec=ModelSpec(alias="openai", provider="openai", model="x"),
                system_prompt="test",
            )
    finally:
        classify_module.call_llm = original


def test_run_classification_rejects_duplicate_section_id() -> None:
    cluster_case = ClusterCase(
        id="tiny",
        template_id="minimal_outpatient_v001",
        cluster_json={
            "topic_label": "test",
            "turns": [
                {"turn_id": 0, "speaker": "MEDICO", "text": "Hola"},
            ],
        },
    )
    template = load_template("minimal_outpatient_v001")

    def fake_call_llm(**_kwargs: object) -> str:
        return '{"section_ids": ["motivo_consulta", "motivo_consulta"]}'

    import classification.classify as classify_module

    original = classify_module.call_llm
    classify_module.call_llm = fake_call_llm
    try:
        with pytest.raises(ValueError, match="duplicate_section_id"):
            run_classification(
                cluster_case=cluster_case,
                template=template,
                model_spec=ModelSpec(alias="openai", provider="openai", model="x"),
                system_prompt="test",
            )
    finally:
        classify_module.call_llm = original
