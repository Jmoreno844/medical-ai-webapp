from __future__ import annotations

from context_pipeline.cluster_spans.prompts.cluster_spans_prompt_v001 import (
    SYSTEM_PROMPT,
    output_schema,
    render_user_payload,
)


def test_system_prompt_references_spans_block() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "<spans>" in SYSTEM_PROMPT
    assert "alergia_penicilina_urticaria" in SYSTEM_PROMPT


def test_render_user_payload_uses_spans_block() -> None:
    payload = render_user_payload(
        spans=[
            {"id": "s1", "text": "Alergia a penicilina: urticaria."},
            {
                "id": "s3",
                "text": "Hemoglobina 9.8 g/dL.",
                "date_hint": "2024-10-11",
            },
        ]
    )
    assert payload.startswith("<spans>")
    assert payload.endswith("</spans>")
    assert '<span id="s1">' in payload
    assert "Alergia a penicilina: urticaria." in payload
    assert 'date_hints="2024-10-11"' in payload
    assert '"doc"' not in payload
    assert '"kind"' not in payload


def test_output_schema_restricts_span_ids() -> None:
    schema = output_schema(span_ids=["s1", "s2"])
    span_id_item = schema["properties"]["clusters"]["items"]["properties"][
        "span_ids"
    ]["items"]
    assert span_id_item["enum"] == ["s1", "s2"]
