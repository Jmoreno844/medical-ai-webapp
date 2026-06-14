from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from classification.lib import ClusterCase, load_cluster_cases
from ui.bridge import clusters_from_clustering_result
from ui.discovery import AI_PIPELINE_ROOT, load_result_json


@dataclass(frozen=True, slots=True)
class ClusterTurnsView:
    cluster_id: str
    topic_label: str
    turns: list[dict[str, object]]


def _resolve_result_file_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None

    candidates = [
        Path(value),
        AI_PIPELINE_ROOT / value,
        AI_PIPELINE_ROOT / "cases" / value,
        AI_PIPELINE_ROOT / "clustering" / value,
        AI_PIPELINE_ROOT / "classification" / value,
        AI_PIPELINE_ROOT / "generation" / value,
    ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def resolve_cases_index_path(payload: dict[str, object]) -> Path | None:
    return _resolve_result_file_path(payload.get("cases_file"))


def resolve_clustering_result_path(payload: dict[str, object]) -> Path | None:
    direct = _resolve_result_file_path(payload.get("clustering_result_file"))
    if direct is not None:
        return direct

    classification_path = _resolve_result_file_path(
        payload.get("classification_result_file")
    )
    if classification_path is None:
        return None

    classification_record = load_result_json(classification_path)
    return _resolve_result_file_path(
        classification_record.get("clustering_result_file")
    )


def load_clusters_index(cases_index: Path) -> dict[str, ClusterCase]:
    return {cluster.id: cluster for cluster in load_cluster_cases(cases_index)}


def _cluster_turns_view_from_case(cluster: ClusterCase) -> ClusterTurnsView:
    topic_label = cluster.cluster_json.get("topic_label")
    turns_raw = cluster.cluster_json.get("turns")
    turns = turns_raw if isinstance(turns_raw, list) else []
    return ClusterTurnsView(
        cluster_id=cluster.id,
        topic_label=topic_label if isinstance(topic_label, str) else cluster.id,
        turns=[turn for turn in turns if isinstance(turn, dict)],
    )


def cluster_turns_index_from_clustering_record(
    record: dict[str, object],
    *,
    session_id: str,
) -> dict[str, ClusterTurnsView]:
    cluster_cases = clusters_from_clustering_result(
        record,
        session_id=session_id.strip(),
        template_id="minimal_outpatient_v001",
    )
    return {
        cluster.id: _cluster_turns_view_from_case(cluster)
        for cluster in cluster_cases
    }


def load_cluster_turns_index(payload: dict[str, object]) -> dict[str, ClusterTurnsView]:
    index: dict[str, ClusterTurnsView] = {}

    cases_index = resolve_cases_index_path(payload)
    if cases_index is not None:
        for cluster_id, cluster in load_clusters_index(cases_index).items():
            index[cluster_id] = _cluster_turns_view_from_case(cluster)

    session_id = payload.get("session_id")
    clustering_path = resolve_clustering_result_path(payload)
    if isinstance(session_id, str) and session_id.strip() and clustering_path is not None:
        clustering_record = json.loads(
            clustering_path.read_text(encoding="utf-8"),
        )
        index.update(
            cluster_turns_index_from_clustering_record(
                clustering_record,
                session_id=session_id,
            )
        )

    return index


def cluster_turns_for_ids(
    *,
    cases_index: Path,
    cluster_ids: list[str],
) -> list[ClusterTurnsView]:
    clusters_by_id = load_clusters_index(cases_index)
    views: list[ClusterTurnsView] = []
    for cluster_id in cluster_ids:
        cluster = clusters_by_id.get(cluster_id)
        if cluster is None:
            views.append(
                ClusterTurnsView(
                    cluster_id=cluster_id,
                    topic_label=cluster_id,
                    turns=[],
                )
            )
            continue
        views.append(_cluster_turns_view_from_case(cluster))
    return views


def cluster_turns_from_generation_payload(
    payload: dict[str, object],
    cluster_ids: list[str],
) -> list[ClusterTurnsView]:
    clusters_by_id = load_cluster_turns_index(payload)
    views: list[ClusterTurnsView] = []
    for cluster_id in cluster_ids:
        cluster_view = clusters_by_id.get(cluster_id)
        if cluster_view is None:
            views.append(
                ClusterTurnsView(
                    cluster_id=cluster_id,
                    topic_label=cluster_id,
                    turns=[],
                )
            )
            continue
        views.append(cluster_view)
    return views


__all__ = [
    "ClusterTurnsView",
    "cluster_turns_for_ids",
    "cluster_turns_from_generation_payload",
    "cluster_turns_index_from_clustering_record",
    "load_cluster_turns_index",
    "load_clusters_index",
    "resolve_cases_index_path",
    "resolve_clustering_result_path",
]
