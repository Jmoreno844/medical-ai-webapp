from __future__ import annotations

import re
import unicodedata

from common.templates import ClinicalTemplate, TemplateSection

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _slugify_heading(heading: str) -> str:
    normalized = unicodedata.normalize("NFKD", heading.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug or "section"


def parse_markdown_template(
    *,
    template_content: str,
    template_id: str,
    template_name: str | None = None,
) -> ClinicalTemplate:
    sections: list[TemplateSection] = []
    seen_ids: dict[str, int] = {}

    for line in template_content.splitlines():
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        if level >= 2:
            base_id = _slugify_heading(heading)
            count = seen_ids.get(base_id, 0)
            seen_ids[base_id] = count + 1
            section_id = base_id if count == 0 else f"{base_id}_{count + 1}"
            sections.append(
                TemplateSection(
                    section_id=section_id,
                    heading=heading,
                    description="",
                )
            )

    if not sections:
        sections = [
            TemplateSection(
                section_id="documento",
                heading="Documento",
                description="",
            )
        ]

    return ClinicalTemplate(
        id=template_id,
        name=template_name or template_id,
        document_kind="clinical",
        sections=sections,
    )
