from __future__ import annotations

from generation.prompts.direct import generation_direct_prompt_v001


def test_render_user_payload_includes_xml_blocks() -> None:
    payload = generation_direct_prompt_v001.render_user_payload(
        section_id="motivo_consulta",
        section_description="Razón de la visita.",
        section_guidelines="Redacta breve.",
        template_guidelines="Markdown clínico.",
        conversation_groups=[[{"patient": "Me duele la cabeza."}]],
        context_brief="",
    )
    assert "Ahora procesa el siguiente caso." in payload
    assert "<section>" in payload
    assert "<guidelines>" in payload
    assert "<template_guidelines>" in payload
    assert "<input_json>" in payload
    assert '"conversation_groups"' in payload
    assert '"context_brief"' in payload
    assert '"turn_id"' not in payload


def test_output_schema_section_id_const() -> None:
    schema = generation_direct_prompt_v001.output_schema(section_id="motivo_consulta")
    assert schema["properties"]["section_id"] == {
        "type": "string",
        "const": "motivo_consulta",
    }
