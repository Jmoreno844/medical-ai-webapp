from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.domains.documents.content import tiptap_json_to_markdown

_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(?P<heading>.+?)\s*$")
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*(?P<heading>[^*\n]{2,120}?)\*\*:?\s*(?P<rest>.*)$")
_ALL_CAPS_HEADING_RE = re.compile(
    r"^\s*(?P<heading>[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9 /()\-.]{2,100})\s*$"
)
_HEADING_NUMBER_PREFIX_RE = re.compile(r"^(?:\d+[.)-]?|[ivxlcdm]+[.)-]?)\s+", re.IGNORECASE)


def _normalize_heading(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _HEADING_NUMBER_PREFIX_RE.sub("", text).rstrip(":.- ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def _slugify_section_id(value: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", _normalize_heading(value)).strip("_")
    return slug or "section"


def _extract_heading_candidate(line: str) -> dict[str, Any] | None:
    markdown_match = _MARKDOWN_HEADING_RE.match(line)
    if markdown_match:
        return {
            "heading": markdown_match.group("heading").strip(),
            "heading_level": len(markdown_match.group(1)),
            "style": "markdown_heading",
        }
    bold_match = _BOLD_HEADING_RE.match(line)
    if bold_match:
        return {
            "heading": bold_match.group("heading").strip(),
            "heading_level": None,
            "style": "bold_heading",
        }
    all_caps_match = _ALL_CAPS_HEADING_RE.match(line)
    if all_caps_match and len(line.strip()) <= 100:
        return {
            "heading": all_caps_match.group("heading").strip(),
            "heading_level": None,
            "style": "all_caps_heading",
        }
    return None


def _unique_section_id(section_id: str, *, existing_ids: set[str]) -> str:
    if section_id not in existing_ids:
        existing_ids.add(section_id)
        return section_id
    suffix = 2
    while f"{section_id}_{suffix}" in existing_ids:
        suffix += 1
    unique_id = f"{section_id}_{suffix}"
    existing_ids.add(unique_id)
    return unique_id


def _content_preview(content: str, *, max_length: int = 220) -> str:
    return " ".join(content.split())[:max_length]


def extract_document_sections(
    *,
    content_markdown: str | None,
    content_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    markdown = str(content_markdown or "")
    if not markdown.strip() and content_json:
        markdown = tiptap_json_to_markdown(content_json)
    if not markdown.strip():
        return {"structure_mode": "unstructured", "sections": []}

    sections: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    line_start = 0
    for line in markdown.splitlines(keepends=True):
        candidate = _extract_heading_candidate(line.rstrip("\n"))
        if candidate:
            section_id = _slugify_section_id(candidate["heading"])
            sections.append(
                {
                    "section_id": _unique_section_id(section_id, existing_ids=seen_ids),
                    "label": candidate["heading"],
                    "heading": candidate["heading"],
                    "normalized_heading": _normalize_heading(candidate["heading"]),
                    "heading_level": candidate["heading_level"],
                    "heading_style": candidate["style"],
                    "resolution_source": "literal_heading",
                    "start_offset": line_start,
                    "content_start_offset": line_start,
                    "end_offset": len(markdown),
                    "content_preview": "",
                }
            )
        line_start += len(line)

    if not sections:
        return {"structure_mode": "unstructured", "sections": []}

    for index, section in enumerate(sections):
        next_start = sections[index + 1]["start_offset"] if index + 1 < len(sections) else len(markdown)
        section["end_offset"] = next_start
        section["content_preview"] = _content_preview(markdown[section["start_offset"] : next_start].strip())

    return {"structure_mode": "structured", "sections": sections}
