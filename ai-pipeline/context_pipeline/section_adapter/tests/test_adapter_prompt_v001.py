from __future__ import annotations

import json

from context_pipeline.section_adapter.prompts.adapter_prompt_v001 import (
    SYSTEM_PROMPT,
    output_schema,
    render_user_payload,
)


def test_system_prompt_describes_brief_not_final_section() -> None:
    assert "brief" in SYSTEM_PROMPT
    assert "Este paso NO genera la sección final" in SYSTEM_PROMPT
    assert "<guidelines>" in SYSTEM_PROMPT
    assert "input_json" not in SYSTEM_PROMPT


def test_render_user_payload_uses_section_guidelines_and_input_json() -> None:
    payload = render_user_payload(
        section_id="antecedentes",
        section_description="Antecedentes médicos.",
        section_guidelines="Incluye:\n- alergias",
        encounter_date="2026-06-14",
        document_date="2024-03-01",
        directives=[{"target": "epicrisis", "action": "use", "hint": None}],
        clusters=[{"id": "c1", "span_ids": ["1"], "date_hints": []}],
        spans=[{"id": "1", "doc": "epicrisis", "kind": "line", "text": "Alergia"}],
    )
    assert payload.startswith("Ahora procesa el siguiente caso.")
    section_pos = payload.index("<section>")
    guidelines_pos = payload.index("<guidelines>")
    input_json_pos = payload.index("<input_json>")
    assert section_pos < guidelines_pos < input_json_pos
    assert "id: antecedentes" in payload
    assert "description: Antecedentes médicos." in payload
    assert "Incluye:" in payload
    input_payload = json.loads(
        payload.split("<input_json>")[1].split("</input_json>")[0].strip()
    )
    assert input_payload["encounter_date"] == "2026-06-14"
    assert input_payload["doc_date"] == "2024-03-01"
    assert input_payload["clusters"][0]["id"] == "c1"
    assert input_payload["spans"][0]["text"] == "Alergia"
    assert "<encounter_context>" not in payload
    assert "<source_spans>" not in payload


def test_output_schema_fixes_section_id() -> None:
    schema = output_schema(section_id="antecedentes")
    assert schema["properties"]["section_id"]["const"] == "antecedentes"
