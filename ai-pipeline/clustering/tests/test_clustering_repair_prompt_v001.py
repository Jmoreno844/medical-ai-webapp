from __future__ import annotations

import json

from clustering.prompts.clustering_repair_prompt_v001 import (
    SYSTEM_PROMPT,
    output_schema,
    render_user_payload,
)


def test_system_prompt_not_empty() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "Haz matching conservador contra los clusters existentes" in SYSTEM_PROMPT
    assert "unassigned_turn_ids" in SYSTEM_PROMPT


def test_render_user_payload_returns_json() -> None:
    existing_clusters = [
        {
            "topic_label": "motivo_consulta",
            "turn_ids": [0, 1],
            "sample_turns": [{"turn_id": 0, "speaker": "medico", "text": "Hola"}],
        }
    ]
    missing_turns = [
        {
            "turn_id": 2,
            "speaker": "medico",
            "text": "¿Desde cuándo?",
            "context_turns": [],
        }
    ]
    payload = render_user_payload(
        existing_clusters=existing_clusters,
        missing_turns=missing_turns,
    )
    parsed = json.loads(payload)
    assert parsed["existing_clusters"] == existing_clusters
    assert parsed["missing_turns"] == missing_turns


def test_output_schema_restricts_turn_ids_and_topic_labels() -> None:
    schema = output_schema(
        missing_turn_ids=[2, 3],
        topic_labels=["motivo_consulta", "medicacion"],
    )
    turn_id_item = schema["properties"]["assignments"]["items"]["properties"]["turn_id"]
    topic_label_item = schema["properties"]["assignments"]["items"]["properties"][
        "topic_label"
    ]
    assert turn_id_item["enum"] == [2, 3]
    assert topic_label_item["enum"] == ["motivo_consulta", "medicacion"]
