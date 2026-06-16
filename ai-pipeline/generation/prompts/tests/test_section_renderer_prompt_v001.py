from __future__ import annotations

from generation.prompts.two_step import section_renderer_prompt_v001


def test_render_user_payload_includes_planned_items() -> None:
    payload = section_renderer_prompt_v001.render_user_payload(
        section_name="Motivo de consulta",
        section_description="Motivo.",
        section_guidelines="Breve.",
        generation_mode="short_single_field",
        template_guidelines="Markdown.",
        planned_items_block="[1] Cefalea de 3 días. evidence: t0",
    )
    assert "name: Motivo de consulta" in payload
    assert "id: motivo_consulta" not in payload
    assert "<planned_items>" in payload
    assert "[1] Cefalea de 3 días. evidence: t0" in payload
    assert "<draft_with_evidence>" not in payload


def test_system_prompt_forbids_section_title_output() -> None:
    prompt = section_renderer_prompt_v001.SYSTEM_PROMPT
    assert "No escribas el título de la sección" in prompt
    assert "No incluyas ningún heading Markdown" in prompt
    assert "La salida no puede contener líneas que empiecen con `#`" in prompt
    assert "### Cardiopulmonar" in prompt
    assert "##Cardiopulmonar: niega falta de aire..." in prompt
    assert "##Análisis clínico: probable origen cardíaco..." in prompt
    assert "Paciente con cansancio de dos semanas" in prompt
    assert "Cardiopulmonar: refiere cansancio al subir escaleras" in prompt
    assert "- Abdominal: refiere molestia epigástrica leve" in prompt
