from __future__ import annotations

from pathlib import Path

from harness.paths import CLUSTER_CASES_INDEX

from ui.cluster_lookup import (
    cluster_turns_for_ids,
    cluster_turns_from_generation_payload,
    resolve_cases_index_path,
    resolve_clustering_result_path,
)


def test_resolve_cases_index_path_absolute() -> None:
    cases_index = CLUSTER_CASES_INDEX
    payload = {"cases_file": str(cases_index)}
    assert resolve_cases_index_path(payload) == cases_index.resolve()


def test_cluster_turns_for_ids_loads_turn_text() -> None:
    cases_index = CLUSTER_CASES_INDEX
    views = cluster_turns_for_ids(
        cases_index=cases_index,
        cluster_ids=["case1_cansancio_escaleras_y_palpidez"],
    )
    assert len(views) == 1
    assert views[0].topic_label == "cansancio_escaleras_y_palpidez"
    assert len(views[0].turns) > 0
    assert "text" in views[0].turns[0]


def test_cluster_turns_from_generation_payload() -> None:
    cases_index = CLUSTER_CASES_INDEX
    payload = {
        "cases_file": str(cases_index),
        "generation_session_result": {
            "sections": [
                {
                    "section_id": "motivo_consulta",
                    "cluster_ids": ["case1_cansancio_escaleras_y_palpidez"],
                }
            ]
        },
    }
    views = cluster_turns_from_generation_payload(
        payload,
        ["case1_cansancio_escaleras_y_palpidez"],
    )
    assert len(views) == 1
    assert views[0].turns


def test_cluster_turns_fallback_to_clustering_result() -> None:
    root = Path(__file__).resolve().parents[2]
    clustering_path = (
        root / "clustering" / "results" / "20260613T035544Z_debug_case1_openai.json"
    )
    if not clustering_path.is_file():
        return

    payload = {
        "session_id": "case1",
        "cases_file": str(CLUSTER_CASES_INDEX),
        "clustering_result_file": str(clustering_path),
    }
    views = cluster_turns_from_generation_payload(
        payload,
        ["case1_mareo_desmayo_bano"],
    )
    assert len(views) == 1
    assert views[0].topic_label == "mareo_desmayo_bano"
    assert views[0].turns
    assert "text" in views[0].turns[0]


def test_resolve_clustering_result_path_from_classification_chain() -> None:
    root = Path(__file__).resolve().parents[2]
    clustering_path = (
        root / "clustering" / "results" / "20260613T035544Z_debug_case1_openai.json"
    )
    if not clustering_path.is_file():
        return

    payload = {
        "classification_result_file": "dummy",
    }
    # Direct path takes precedence when provided
    resolved = resolve_clustering_result_path(
        {
            "clustering_result_file": str(clustering_path),
        }
    )
    assert resolved == clustering_path.resolve()

