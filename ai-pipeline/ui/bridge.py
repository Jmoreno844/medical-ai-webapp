from __future__ import annotations

import copy
from pathlib import Path

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.common.context_claims import (
    ClaimAssignment,
    ClinicalClaim,
    group_claims_by_section,
)
from document_pipeline_core.common.transcripts import build_turn_catalog
from document_pipeline_core.generation.lib import load_section_context_from_record
from ui.discovery import load_result_json


def apply_filtering_to_transcript(
    transcript_json: dict[str, object],
    drop_turn_ids: list[int],
) -> dict[str, object]:
    catalog = build_turn_catalog(transcript_json)
    drop_set = set(drop_turn_ids)
    kept_turns: list[dict[str, object]] = []
    for turn in catalog:
        turn_id = turn["turn_id"]
        if isinstance(turn_id, int) and turn_id in drop_set:
            continue
        kept_turns.append(
            {
                "turn_id": turn["turn_id"],
                "speaker": turn["speaker"],
                "text": turn["text"],
            }
        )

    renumbered_turns: list[dict[str, object]] = []
    for new_turn_id, turn in enumerate(kept_turns):
        renumbered_turns.append(
            {
                "turn_id": new_turn_id,
                "speaker": turn["speaker"],
                "text": turn["text"],
            }
        )

    filtered = copy.deepcopy(transcript_json)
    filtered["chunks"] = [{"chunk_id": "s0", "turns": renumbered_turns}]
    return filtered


def drop_turn_ids_from_filtering_result(payload: dict[str, object]) -> list[int]:
    filtering_result = payload.get("filtering_result")
    if not isinstance(filtering_result, dict):
        raise ValueError("filtering_result_missing")
    drop_turn_ids = filtering_result.get("drop_turn_ids")
    if not isinstance(drop_turn_ids, list):
        raise ValueError("filtering_drop_turn_ids_missing")
    return [int(turn_id) for turn_id in drop_turn_ids]


def clusters_from_clustering_result(
    payload: dict[str, object],
    *,
    session_id: str,
    template_id: str,
) -> list[ClusterCase]:
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ValueError("clustering_bridge_session_id_must_be_non_empty")
    normalized_template_id = template_id.strip()
    if not normalized_template_id:
        raise ValueError("clustering_bridge_template_id_must_be_non_empty")

    clustering_result = payload.get("clustering_result")
    if not isinstance(clustering_result, dict):
        raise ValueError("clustering_result_missing")
    clusters_raw = clustering_result.get("clusters")
    if not isinstance(clusters_raw, list):
        raise ValueError("clustering_clusters_missing")

    clusters: list[ClusterCase] = []
    for index, item in enumerate(clusters_raw):
        if not isinstance(item, dict):
            raise ValueError(f"clustering_cluster_{index}_must_be_object")
        topic_label = item.get("topic_label")
        if not isinstance(topic_label, str) or not topic_label.strip():
            raise ValueError(f"clustering_cluster_{index}_topic_label_missing")
        turns = item.get("turns")
        if not isinstance(turns, list):
            raise ValueError(f"clustering_cluster_{index}_turns_missing")

        cluster_id = f"{normalized_session_id}_{topic_label.strip()}"
        cluster_json: dict[str, object] = {
            "session_id": normalized_session_id,
            "topic_label": topic_label.strip(),
            "turns": turns,
        }
        clusters.append(
            ClusterCase(
                id=cluster_id,
                cluster_json=cluster_json,
                template_id=normalized_template_id,
            )
        )

    if not clusters:
        raise ValueError("clustering_bridge_requires_at_least_one_cluster")
    return sorted(clusters, key=lambda cluster: cluster.id)


def assignment_cluster_ids_from_classification_record(
    classification_record: dict[str, object],
) -> list[str]:
    session_result = classification_record.get("classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("classification_session_result_missing")
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("classification_assignments_missing")

    cluster_ids: list[str] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"classification_assignment_{index}_must_be_object")
        cluster_id = item.get("cluster_id")
        if not isinstance(cluster_id, str) or not cluster_id.strip():
            raise ValueError(f"classification_assignment_{index}_cluster_id_missing")
        cluster_ids.append(cluster_id.strip())
    return cluster_ids


def missing_assignment_cluster_ids(
    *,
    assignment_cluster_ids: list[str],
    clusters: list[ClusterCase],
) -> list[str]:
    available_ids = {cluster.id for cluster in clusters}
    return sorted(
        {
            cluster_id
            for cluster_id in assignment_cluster_ids
            if cluster_id not in available_ids
        }
    )


def resolve_clustering_result_path_from_classification_record(
    classification_record: dict[str, object],
) -> Path | None:
    clustering_file = classification_record.get("clustering_result_file")
    if not isinstance(clustering_file, str) or not clustering_file.strip():
        return None
    path = Path(clustering_file.strip())
    if path.is_file():
        return path.resolve()

    from ui.cluster_lookup import _resolve_result_file_path

    return _resolve_result_file_path(clustering_file)


def clusters_from_classification_record(
    classification_record: dict[str, object],
) -> tuple[list[ClusterCase], Path]:
    session_id = classification_record.get("session_id")
    template_id = classification_record.get("template_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("classification_session_id_missing")
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError("classification_template_id_missing")

    clustering_path = resolve_clustering_result_path_from_classification_record(
        classification_record
    )
    if clustering_path is None:
        raise ValueError("classification_clustering_result_file_missing")

    clustering_record = load_result_json(clustering_path)
    clusters = clusters_from_clustering_result(
        clustering_record,
        session_id=session_id.strip(),
        template_id=template_id.strip(),
    )
    return clusters, clustering_path


def claims_by_section_from_classification_record(
    record: dict[str, object],
) -> dict[str, list[ClinicalClaim]]:
    claims_raw = record.get("claims")
    if not isinstance(claims_raw, list):
        raise ValueError("claim_classification_claims_missing")
    claims = [
        ClinicalClaim.model_validate(item)
        for item in claims_raw
        if isinstance(item, dict)
    ]
    claims_by_id = {claim.claim_id: claim for claim in claims}
    session_result = record.get("claim_classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("claim_classification_session_result_missing")
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("claim_classification_assignments_missing")
    assignments = [
        ClaimAssignment.model_validate(item)
        for item in assignments_raw
        if isinstance(item, dict)
    ]
    section_ids = {
        section_id
        for assignment in assignments
        for section_id in assignment.section_ids
    }
    return group_claims_by_section(assignments, claims_by_id, section_ids)


__all__ = [
    "apply_filtering_to_transcript",
    "assignment_cluster_ids_from_classification_record",
    "claims_by_section_from_classification_record",
    "clusters_from_classification_record",
    "clusters_from_clustering_result",
    "drop_turn_ids_from_filtering_result",
    "load_section_context_from_record",
    "missing_assignment_cluster_ids",
    "resolve_clustering_result_path_from_classification_record",
]
