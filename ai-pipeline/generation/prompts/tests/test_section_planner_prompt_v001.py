from __future__ import annotations

from generation.prompts.two_step import section_planner_prompt_v001


def test_render_user_payload_includes_evidence_block() -> None:
    payload = section_planner_prompt_v001.render_user_payload(
        section_id="motivo_consulta",
        section_description="Motivo.",
        section_guidelines="Breve.",
        template_guidelines="Markdown.",
        evidence_block="Consulta actual:\n[t0] patient: Cefalea.",
    )
    assert "Ahora procesa el siguiente caso." in payload
    assert "<evidence>" in payload
    assert '"items"' in section_planner_prompt_v001.SYSTEM_PROMPT
    assert "[t0] patient: Cefalea." in payload


def test_output_schema_evidence_enum() -> None:
    schema = section_planner_prompt_v001.output_schema(
        allowed_evidence_ids=["t0", "s1"],
    )
    evidence_items = schema["properties"]["items"]["items"]["properties"]["e"]["items"]
    assert evidence_items["enum"] == ["s1", "t0"]


def test_system_prompt_forbids_placeholder_items_without_evidence() -> None:
    prompt = section_planner_prompt_v001.SYSTEM_PROMPT
    assert "No completes subcampos esperados" in prompt
    assert "omítelo por completo" in prompt
    assert 'Nunca devuelvas un item con "e": []' in prompt
    assert "sin datos aportados" in prompt
    assert "Una negación explícita sí puede incluirse" in prompt
