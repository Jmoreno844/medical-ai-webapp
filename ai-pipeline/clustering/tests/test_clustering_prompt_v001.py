from __future__ import annotations

import json

from clustering.prompts.clustering_prompt_v001 import SYSTEM_PROMPT, output_schema, render_user_payload


def test_system_prompt_not_empty() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "Agrupa por tema, no por cercanía" in SYSTEM_PROMPT
    assert "topic_label" in SYSTEM_PROMPT


def test_render_user_payload_wraps_transcript_block() -> None:
    turns = [{"turn_id": 0, "speaker": "medico", "text": "Hola"}]
    payload = render_user_payload(turns=turns)
    assert payload.startswith("<transcript>")
    assert payload.endswith("</transcript>")
    inner = payload.removeprefix("<transcript>\n").removesuffix("\n</transcript>")
    parsed = json.loads(inner)
    assert parsed["turns"] == turns


def test_output_schema_restricts_turn_ids_to_known_turns() -> None:
    schema = output_schema(turn_ids=[0, 1, 2])
    turn_id_item = schema["properties"]["clusters"]["items"]["properties"]["turn_ids"][
        "items"
    ]
    assert turn_id_item["enum"] == [0, 1, 2]
