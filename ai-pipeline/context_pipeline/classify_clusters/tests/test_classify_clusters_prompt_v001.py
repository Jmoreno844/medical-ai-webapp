from __future__ import annotations

from context_pipeline.classify_clusters.prompts.classify_clusters_prompt_v001 import (
    SYSTEM_PROMPT,
    output_schema,
    render_user_payload,
)


def test_system_prompt_not_empty() -> None:
    assert SYSTEM_PROMPT.strip()
    assert "section_ids: []" in SYSTEM_PROMPT
    assert "<template_sections>" in SYSTEM_PROMPT
    assert "<source_spans>" in SYSTEM_PROMPT


def test_render_user_payload_uses_semantic_blocks_in_order() -> None:
    payload = render_user_payload(
        template_sections=[
            {
                "section_id": "antecedentes",
                "heading": "Antecedentes",
                "description": "Antecedentes médicos.",
                "guidelines": "- Incluye alergias.",
            }
        ],
        encounter_date="2026-06-14",
        document_date="2024-03-01",
        clusters=[{"id": "c1", "span_ids": ["s1"], "date_hints": []}],
        spans=[{"id": "s1", "doc": "doc", "kind": "body", "text": "Hola"}],
    )
    encounter_pos = payload.index("<encounter_context>")
    template_pos = payload.index("<template_sections>")
    clusters_pos = payload.index("<clusters>")
    spans_pos = payload.index("<source_spans>")
    assert encounter_pos < template_pos < clusters_pos < spans_pos
    assert "encounter_date: 2026-06-14" in payload
    assert "doc_date: 2024-03-01" in payload
    assert '<section id="antecedentes">' in payload
    assert "classification_guidelines:" in payload
    assert '<cluster id="c1">' in payload
    assert 'span_ids: ["s1"]' in payload
    assert '<span id="s1" doc="doc" kind="body">' in payload
    assert "Hola" in payload
    assert "date_hint:" not in payload


def test_output_schema_restricts_cluster_and_section_ids() -> None:
    schema = output_schema(cluster_ids=["c1", "c2"], section_ids=["antecedentes"])
    assignment_item = schema["properties"]["assignments"]["items"]
    assert assignment_item["properties"]["cluster_id"]["enum"] == ["c1", "c2"]
    assert (
        assignment_item["properties"]["section_ids"]["items"]["enum"]
        == ["antecedentes"]
    )
    assert schema["properties"]["assignments"]["minItems"] == 2
