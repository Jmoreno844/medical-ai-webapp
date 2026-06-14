from __future__ import annotations

import copy

from classification.lib import ClusterCase
from common.transcripts import TranscriptCase, build_turn_catalog
from generation.lib import ClusterAssignmentInput


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


def clusters_from_clustering_result(
    clustering_result: dict[str, object],
    *,
    session_id: str,
    template_id: str,
) -> list[ClusterCase]:
    normalized_session_id = session_id.strip()
    normalized_template_id = template_id.strip()
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


def assignments_from_classification_session(
  session_result: dict[str, object],
) -> list[ClusterAssignmentInput]:
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("classification_assignments_missing")
    assignments: list[ClusterAssignmentInput] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"classification_assignment_{index}_must_be_object")
        cluster_id = item.get("cluster_id")
        section_ids = item.get("section_ids")
        if not isinstance(cluster_id, str):
            raise ValueError(f"classification_assignment_{index}_cluster_id_missing")
        if not isinstance(section_ids, list):
            raise ValueError(f"classification_assignment_{index}_section_ids_missing")
        assignments.append(
            ClusterAssignmentInput(
                cluster_id=cluster_id,
                section_ids=[str(section_id) for section_id in section_ids],
            )
        )
    return assignments


def build_transcript_json(
    *,
    session_id: str,
    turns: list[dict[str, object]],
) -> dict[str, object]:
    catalog_turns: list[dict[str, object]] = []
    for index, turn in enumerate(turns):
        speaker = turn.get("speaker")
        text = turn.get("text")
        if not isinstance(speaker, str) or not isinstance(text, str):
            continue
        turn_id = turn.get("turn_id")
        resolved_turn_id = int(turn_id) if isinstance(turn_id, int) else index
        catalog_turns.append(
            {
                "turn_id": resolved_turn_id,
                "speaker": speaker,
                "text": text,
            }
        )
    return {
        "session_id": session_id,
        "chunks": [{"chunk_id": "s0", "turns": catalog_turns}],
    }


def transcript_case_from_filtering(
    *,
    base_case: TranscriptCase,
    drop_turn_ids: list[int],
) -> TranscriptCase:
    filtered_json = apply_filtering_to_transcript(base_case.transcript_json, drop_turn_ids)
    return TranscriptCase(
        id=base_case.id,
        transcript_json=filtered_json,
        notes=base_case.notes,
    )
