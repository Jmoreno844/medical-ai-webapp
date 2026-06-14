from __future__ import annotations

from app.pipeline.generation.lib import (
    normalize_section_generation_content,
    render_generated_section_markdown,
)


def test_normalize_section_generation_content_strips_duplicate_heading() -> None:
    content = "## Motivo de consulta\n\nMotivo de consulta: cefalea"
    assert (
        normalize_section_generation_content(content, heading="Motivo de consulta")
        == "Motivo de consulta: cefalea"
    )


def test_render_generated_section_markdown_skips_empty_sections() -> None:
    assert (
        render_generated_section_markdown("## Motivo de consulta\n\n", heading="Motivo de consulta")
        is None
    )
    assert (
        render_generated_section_markdown("Motivo de consulta: cefalea", heading="Motivo de consulta")
        == "## Motivo de consulta\n\nMotivo de consulta: cefalea\n"
    )
