from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_pipeline_core.common.transcripts import build_turn_catalog, load_cases, select_cases
from ui.bridge import (
    apply_filtering_to_transcript,
    clusters_from_classification_record,
    clusters_from_clustering_result,
    drop_turn_ids_from_filtering_result,
    missing_assignment_cluster_ids,
)


def test_apply_filtering_to_transcript_renumbers_turns() -> None:
    transcript = {
        "session_id": "case2",
        "chunks": [
            {
                "chunk_id": "s0",
                "turns": [
                    {"turn_id": 0, "speaker": "MEDICO", "text": "hola"},
                    {"turn_id": 1, "speaker": "PACIENTE", "text": "hola"},
                    {"turn_id": 2, "speaker": "MEDICO", "text": "motivo"},
                ],
            }
        ],
    }
    filtered = apply_filtering_to_transcript(transcript, [0, 1])
    catalog = build_turn_catalog(filtered)
    assert len(catalog) == 1
    assert catalog[0]["turn_id"] == 0
    assert catalog[0]["text"] == "motivo"


def test_drop_turn_ids_from_filtering_result() -> None:
    payload = {"filtering_result": {"drop_turn_ids": [1, 3]}}
    assert drop_turn_ids_from_filtering_result(payload) == [1, 3]


def test_clusters_from_clustering_result_matches_fixture_shape() -> None:
    result_path = (
        Path(__file__).resolve().parents[2]
        / "clustering"
        / "results"
        / "20260612T213837Z_debug_case1_openai.json"
    )
    if not result_path.is_file():
        pytest.skip("clustering result fixture not available")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    clusters = clusters_from_clustering_result(
        payload,
        session_id="case1",
        template_id="minimal_outpatient_v001",
    )
    assert len(clusters) == 12
    assert clusters[0].id.startswith("case1_")
    assert clusters[0].cluster_json["session_id"] == "case1"
    assert "turns" in clusters[0].cluster_json


def test_apply_filtering_matches_case2_filtered_fixture() -> None:
    cases_index = Path(__file__).resolve().parents[2] / "cases" / "index.json"
    case2 = select_cases(load_cases(cases_index), case_id="case2")[0]
    filtered_case = select_cases(
        load_cases(cases_index),
        case_id="case2_filtered",
    )[0]
    filtering_result_path = (
        Path(__file__).resolve().parents[2]
        / "filtering"
        / "results"
        / "20260612T211045Z_debug_case2_openai.json"
    )
    if not filtering_result_path.is_file():
        pytest.skip("filtering result fixture not available")
    filtering_payload = json.loads(
        filtering_result_path.read_text(encoding="utf-8")
    )
    drop_ids = drop_turn_ids_from_filtering_result(filtering_payload)
    filtered_transcript = apply_filtering_to_transcript(
        case2.transcript_json,
        drop_ids,
    )
    assert build_turn_catalog(filtered_transcript) == build_turn_catalog(
        filtered_case.transcript_json
    )


def test_clusters_from_classification_record_links_clustering_file() -> None:
    classification_path = (
        Path(__file__).resolve().parents[2]
        / "classification"
        / "results"
        / "20260613T040410Z_session_case1_groq.json"
    )
    if not classification_path.is_file():
        pytest.skip("classification result fixture not available")

    payload = json.loads(classification_path.read_text(encoding="utf-8"))
    clusters, clustering_path = clusters_from_classification_record(payload)
    assert clustering_path.name == "20260613T040406Z_debug_case1_openai.json"
    cluster_ids = {cluster.id for cluster in clusters}
    assert "case1_cansancio_escaleras_y_palidez" in cluster_ids


def test_fixtures_do_not_match_fresh_classification_cluster_ids() -> None:
    classification_path = (
        Path(__file__).resolve().parents[2]
        / "classification"
        / "results"
        / "20260613T040410Z_session_case1_groq.json"
    )
    if not classification_path.is_file():
        pytest.skip("classification result fixture not available")

    from harness.paths import CLUSTER_CASES_INDEX
    from document_pipeline_core.classification.lib import load_session_clusters
    from ui.bridge import assignment_cluster_ids_from_classification_record

    payload = json.loads(classification_path.read_text(encoding="utf-8"))
    assignment_ids = assignment_cluster_ids_from_classification_record(payload)
    fixture_clusters = load_session_clusters(CLUSTER_CASES_INDEX, "case1")
    missing = missing_assignment_cluster_ids(
        assignment_cluster_ids=assignment_ids,
        clusters=fixture_clusters,
    )
    assert "case1_cansancio_escaleras_y_palidez" in missing
