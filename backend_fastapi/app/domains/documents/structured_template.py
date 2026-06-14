from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.domains.documents.schemas import (
    ClinicalTemplateOut,
    StepGuidelinesOut,
    TemplateSectionOut,
)

TEMPLATE_ID = "consulta_estructurada_v001"
TEMPLATE_NAME = "Consulta estructurada"
TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / f"{TEMPLATE_ID}.json"
)


@lru_cache(maxsize=1)
def load_consulta_estructurada_template_json() -> dict[str, object]:
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"clinical_template_not_found: {TEMPLATE_PATH}")
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("clinical_template_json_must_be_object")
    return payload


def _guidelines_out(raw: object) -> StepGuidelinesOut:
    if not isinstance(raw, dict):
        return StepGuidelinesOut()
    guidelines = raw.get("guidelines")
    if isinstance(guidelines, str):
        return StepGuidelinesOut(guidelines=guidelines)
    return StepGuidelinesOut()


def markdown_content_from_template_json(data: dict[str, object]) -> str:
    lines: list[str] = []
    sections = data.get("sections")
    if not isinstance(sections, list):
        return ""
    for item in sections:
        if not isinstance(item, dict):
            continue
        heading = item.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            continue
        lines.append(f"## {heading.strip()}")
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            lines.append(description.strip())
        lines.append("")
    return "\n".join(lines).strip()


def clinical_template_out_from_json(
    data: dict[str, object],
    *,
    template_id: str | None = None,
    template_name: str | None = None,
) -> ClinicalTemplateOut:
    sections_raw = data.get("sections")
    sections: list[TemplateSectionOut] = []
    if isinstance(sections_raw, list):
        for item in sections_raw:
            if not isinstance(item, dict):
                continue
            section_id = item.get("section_id")
            heading = item.get("heading")
            if not isinstance(section_id, str) or not isinstance(heading, str):
                continue
            description = item.get("description")
            sections.append(
                TemplateSectionOut(
                    section_id=section_id.strip(),
                    heading=heading.strip(),
                    description=description.strip()
                    if isinstance(description, str)
                    else "",
                    classification=_guidelines_out(item.get("classification")),
                    generation=_guidelines_out(item.get("generation")),
                )
            )

    document_kind = data.get("document_kind")
    return ClinicalTemplateOut(
        id=template_id or str(data.get("id") or TEMPLATE_ID),
        name=template_name or str(data.get("name") or TEMPLATE_NAME),
        document_kind=document_kind.strip()
        if isinstance(document_kind, str) and document_kind.strip()
        else "document",
        classification=_guidelines_out(data.get("classification")),
        generation=_guidelines_out(data.get("generation")),
        sections=sections,
    )


def default_clinical_template_out(
    *,
    template_name: str | None = None,
) -> ClinicalTemplateOut:
    return clinical_template_out_from_json(
        load_consulta_estructurada_template_json(),
        template_id=TEMPLATE_ID,
        template_name=template_name,
    )
