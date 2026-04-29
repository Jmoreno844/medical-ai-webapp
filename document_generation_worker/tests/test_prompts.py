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
