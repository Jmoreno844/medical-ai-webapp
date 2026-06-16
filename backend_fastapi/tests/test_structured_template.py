from __future__ import annotations

from app.domains.documents.structured_template import (
    TEMPLATE_ID,
    clinical_template_out_from_json,
    load_consulta_estructurada_template_json,
    markdown_content_from_template_json,
)


def test_consulta_estructurada_markdown_has_all_section_headings() -> None:
    data = load_consulta_estructurada_template_json()
    markdown = markdown_content_from_template_json(data)
    assert "## Identificación" in markdown
    assert "## Análisis y plan" in markdown
    assert markdown.count("## ") == 10


def test_clinical_template_out_preserves_section_ids_and_guidelines() -> None:
    data = load_consulta_estructurada_template_json()
    template = clinical_template_out_from_json(data)
    assert template.id == TEMPLATE_ID
    assert len(template.sections) == 10
    assert template.sections[0].section_id == "identificacion"
    assert template.classification.guidelines
    assert template.generation.guidelines
    assert template.sections[1].heading == "Motivo de consulta"
