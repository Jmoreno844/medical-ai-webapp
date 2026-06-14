from __future__ import annotations

from context_pipeline.filter_spans.prompts.filter_spans_prompt_v001 import (
    SYSTEM_PROMPT,
    output_schema,
    render_user_payload,
)


def test_system_prompt_not_empty() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "Ante la duda, no descartes" in SYSTEM_PROMPT
    assert "drop_ids" in SYSTEM_PROMPT


def test_render_user_payload_returns_json() -> None:
    spans = [{"id": "s1", "doc": "doc", "kind": "line", "text": "Hola"}]
    payload = render_user_payload(
        encounter_date="2026-06-14",
        document_date="2024-03-01",
        directives=[],
        spans=spans,
    )
    assert '"encounter_date": "2026-06-14"' in payload
    assert '"document_date": "2024-03-01"' in payload
    assert '"id": "s1"' in payload


def test_output_schema_restricts_drop_ids_to_known_spans() -> None:
    schema = output_schema(span_ids=["s1", "s2"])
    enum_values = schema["properties"]["drop_ids"]["items"]["enum"]
    assert enum_values == ["s1", "s2"]
