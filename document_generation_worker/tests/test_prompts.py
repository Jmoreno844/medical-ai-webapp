from app.prompts import build_document_prompt


def test_build_document_prompt_contains_sections_without_losing_lengths() -> None:
    prompt = build_document_prompt(
        template_content="## Motivo",
        context_content="No se agregó contexto.",
        transcription_content="Paciente refiere dolor.",
    )

    assert "## Motivo" in prompt
    assert "No se agregó contexto." in prompt
    assert "Paciente refiere dolor." in prompt


def test_build_document_prompt_includes_prudent_clinical_safety_rules() -> None:
    prompt = build_document_prompt(
        template_content="## Analisis",
        context_content="Medico considera falla cardiaca a descartar.",
        transcription_content="Paciente con disnea.",
    )

    assert "No conviertas una sospecha" in prompt
    assert 'redacta con lenguaje prudente como "impresión clínica"' in prompt
    assert "No infieras frases clínicas de mayor certeza" in prompt
