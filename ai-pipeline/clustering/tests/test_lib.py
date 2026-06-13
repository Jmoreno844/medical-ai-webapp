from __future__ import annotations

import json

from clustering.lib import (
    DEFAULT_CASES_INDEX,
    ClusteringResult,
    audit_turn_coverage,
    enrich_clustering_result_for_export,
    format_clustering_output_for_detail,
    parse_clustering_result,
    prompt_file_path,
)


def test_parse_clustering_result() -> None:
    raw = json.dumps(
        {
            "clusters": [
                {
                    "topic_label": "medicacion",
                    "turn_ids": [0, 1],
                }
            ],
            "unassigned_turn_ids": [],
        }
    )
    result = parse_clustering_result(raw)
    assert isinstance(result, ClusteringResult)
    assert result.clusters[0].topic_label == "medicacion"
    assert result.clusters[0].turn_ids == [0, 1]


def test_prompt_file_path() -> None:
    path = prompt_file_path("v001")
    assert path.name == "clustering_v001.txt"
    assert path.is_file()


def test_enrich_clustering_result_for_export_includes_turn_text() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "Buenos dias"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "Cansancio"},
    ]
    result = ClusteringResult(
        clusters=[{"topic_label": "cansancio", "turn_ids": [0, 1]}],
        unassigned_turn_ids=[],
    )
    exported = enrich_clustering_result_for_export(result, catalog)
    assert exported["clusters"][0]["turns"][1]["text"] == "Cansancio"
    assert exported["clusters"][0]["turn_ids"] == [0, 1]


def test_audit_turn_coverage_detects_missing_turn_ids() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "cansancio"},
        {"turn_id": 2, "speaker": "MEDICO", "text": "desde cuando"},
    ]
    result = ClusteringResult(
        clusters=[{"topic_label": "motivo_consulta", "turn_ids": [0, 1]}],
        unassigned_turn_ids=[],
    )
    audit = audit_turn_coverage(result, catalog)
    assert audit.missing_turn_ids == [2]
    assert audit.extra_turn_ids == []
    assert audit.duplicate_turn_ids == []
    assert not audit.is_complete


def test_audit_turn_coverage_detects_duplicates() -> None:
    catalog = [
        {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
        {"turn_id": 1, "speaker": "PACIENTE", "text": "cansancio"},
    ]
    result = ClusteringResult(
        clusters=[{"topic_label": "motivo_consulta", "turn_ids": [0, 1, 1]}],
        unassigned_turn_ids=[],
    )
    audit = audit_turn_coverage(result, catalog)
    assert audit.missing_turn_ids == []
    assert audit.duplicate_turn_ids == [1]
    assert not audit.is_complete


def test_compact_output_detail_omits_raw_response() -> None:
    payload = {
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "clustering_result": {"clusters": [], "unassigned_turn_ids": []},
        "turn_coverage": {
            "is_complete": False,
            "missing_turn_ids": [2],
            "extra_turn_ids": [],
            "duplicate_turn_ids": [],
        },
        "raw_response": "{\"clusters\": []}",
    }
    compact = format_clustering_output_for_detail(payload, "compact")
    assert "raw_response" not in compact
    assert compact["clustering_result"]["clusters"] == []
    assert compact["turn_coverage"]["missing_turn_ids"] == [2]


def test_default_cases_index_points_to_shared_cases() -> None:
    assert DEFAULT_CASES_INDEX.name == "index.json"
    assert DEFAULT_CASES_INDEX.parent.name == "cases"
    assert DEFAULT_CASES_INDEX.is_file()
