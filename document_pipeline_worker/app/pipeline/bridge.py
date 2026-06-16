from __future__ import annotations

from document_pipeline_core.orchestrators.bridge import (
    apply_filtering_to_transcript,
    assignments_from_classification_session,
    clusters_from_clustering_result,
    transcript_case_from_filtering,
)


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


__all__ = [
    "apply_filtering_to_transcript",
    "assignments_from_classification_session",
    "build_transcript_json",
    "clusters_from_clustering_result",
    "transcript_case_from_filtering",
]
