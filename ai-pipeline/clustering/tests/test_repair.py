from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from clustering.lib import ClusteringResult, audit_turn_coverage
from clustering.repair import (
    apply_repair_assignments,
    build_repair_user_payload,
    clustering_repair_output_schema,
    clustering_repair_prompt_reference,
    load_clustering_repair_prompt,
    parse_clustering_repair_result,
    repair_clustering_coverage,
)


def test_build_repair_user_payload_includes_missing_turn_text_and_context() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "¿Dolor?"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "No"},
        {"turn_id": 2, "speaker": "MEDICO", "text": "¿Presión?"},
        {"turn_id": 3, "speaker": "PACIENTE", "text": "Sí, leve"},
    ]
    result = ClusteringResult(
        clusters=[
            {"topic_label": "motivo_consulta", "turn_ids": [0, 1]},
        ],
        unassigned_turn_ids=[],
    )
    payload = json.loads(
        build_repair_user_payload(
            result=result,
            catalog=catalog,
            missing_turn_ids=[2, 3],
            context_window=1,
        )
    )
    assert payload["existing_clusters"][0]["topic_label"] == "motivo_consulta"
    assert payload["missing_turns"][0]["text"] == "¿Presión?"
    assert payload["missing_turns"][0]["context_turns"][0]["turn_id"] == 1


def test_load_clustering_repair_prompt_v002_returns_py_system_prompt() -> None:
    from clustering.prompts.clustering_repair_prompt_v001 import SYSTEM_PROMPT

    assert load_clustering_repair_prompt("v002") == SYSTEM_PROMPT.strip()


def test_clustering_repair_output_schema_v002_restricts_labels() -> None:
    schema = clustering_repair_output_schema(
        missing_turn_ids=[2],
        topic_labels=["motivo_consulta"],
        prompt_version="v002",
    )
    assert schema is not None
    topic_label_item = schema["properties"]["assignments"]["items"]["properties"][
        "topic_label"
    ]
    assert topic_label_item["enum"] == ["motivo_consulta"]


def test_clustering_repair_prompt_reference_v002_points_to_py_module() -> None:
    assert (
        clustering_repair_prompt_reference("v002")
        == "clustering/prompts/clustering_repair_prompt_v001.py"
    )


def test_apply_repair_assignments_merges_missing_turns() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "cansancio"},
        {"turn_id": 2, "speaker": "MEDICO", "text": "desde cuando"},
    ]
    result = ClusteringResult(
        clusters=[{"topic_label": "motivo_consulta", "turn_ids": [0, 1]}],
        unassigned_turn_ids=[],
    )
    repair = parse_clustering_repair_result(
        json.dumps(
            {
                "assignments": [
                    {"turn_id": 2, "topic_label": "motivo_consulta"},
                ],
                "unassigned_turn_ids": [],
            }
        )
    )
    repaired = apply_repair_assignments(
        result,
        repair,
        missing_turn_ids=[2],
    )
    audit = audit_turn_coverage(repaired, catalog)
    assert audit.is_complete
    assert repaired.clusters[0].turn_ids == [0, 1, 2]


def test_apply_repair_assignments_rejects_unknown_topic_label() -> None:
    result = ClusteringResult(
        clusters=[{"topic_label": "motivo_consulta", "turn_ids": [0]}],
        unassigned_turn_ids=[],
    )
    repair = parse_clustering_repair_result(
        json.dumps(
            {
                "assignments": [{"turn_id": 1, "topic_label": "otro_cluster"}],
                "unassigned_turn_ids": [],
            }
        )
    )
    with pytest.raises(ValueError, match="unknown_topic_label"):
        apply_repair_assignments(result, repair, missing_turn_ids=[1])


def test_repair_clustering_coverage_without_llm_is_noop_when_complete() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "cansancio"},
    ]
    result = ClusteringResult(
        clusters=[{"topic_label": "motivo_consulta", "turn_ids": [0, 1]}],
        unassigned_turn_ids=[],
    )

    def _should_not_call_llm(**_kwargs: object) -> str:
        raise AssertionError("repair LLM should not be called when coverage is complete")

    repaired, repair_passes = repair_clustering_coverage(
        result=result,
        catalog=catalog,
        model_spec=Mock(),
        repair_system_prompt="ignored",
        max_repair_passes=2,
    )
    assert repaired == result
    assert repair_passes == []
