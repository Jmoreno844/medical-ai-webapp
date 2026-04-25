from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

PreferredContentSource = Literal["markdown", "json"]

_EMPTY_DOC: dict[str, Any] = {
    "type": "doc",
    "content": [{"type": "paragraph"}],
}


@dataclass(frozen=True)
class SyncedDocumentContent:
    content_markdown: str
    content_json: dict[str, Any]


def get_empty_tiptap_doc() -> dict[str, Any]:
    return deepcopy(_EMPTY_DOC)


def normalize_markdown(content: str | None) -> str:
    if not content:
        return ""
    return str(content).replace("\r\n", "\n").replace("\r", "\n")


def normalize_tiptap_document(content_json: dict[str, Any] | None) -> dict[str, Any]:
    if content_json is None:
        return get_empty_tiptap_doc()
    if not isinstance(content_json, dict):
        raise ValueError("content_json debe ser un objeto JSON")

    normalized = deepcopy(content_json)
    if normalized.get("type") == "doc":
        content = normalized.get("content")
        if not isinstance(content, list) or len(content) == 0:
            return get_empty_tiptap_doc()
        return normalized
    return {"type": "doc", "content": [normalized]}


def build_synced_document_content(
    *,
    content_markdown: str | None = None,
    content_json: dict[str, Any] | None = None,
    preferred_source: PreferredContentSource = "markdown",
) -> SyncedDocumentContent:
    if preferred_source == "json" and content_json is not None:
        normalized_json = normalize_tiptap_document(content_json)
        return SyncedDocumentContent(
            content_markdown=tiptap_json_to_markdown(normalized_json),
            content_json=normalized_json,
        )

    normalized_markdown = normalize_markdown(content_markdown)
    return SyncedDocumentContent(
        content_markdown=normalized_markdown,
        content_json=markdown_to_tiptap_json(normalized_markdown),
    )


def set_document_content_fields(
    document: Any,
    *,
    content_markdown: str | None = None,
    content_json: dict[str, Any] | None = None,
    preferred_source: PreferredContentSource = "markdown",
) -> SyncedDocumentContent:
    synced = build_synced_document_content(
        content_markdown=content_markdown,
        content_json=content_json,
        preferred_source=preferred_source,
    )
    document.content_markdown = synced.content_markdown
    document.content_json = synced.content_json
    return synced


def markdown_to_tiptap_json(markdown: str | None) -> dict[str, Any]:
    normalized = normalize_markdown(markdown)
    if normalized == "":
        return get_empty_tiptap_doc()

    paragraphs = []
    for block in normalized.split("\n\n"):
        text = block.strip()
        if not text:
            continue
        paragraphs.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        )
    return {"type": "doc", "content": paragraphs or [{"type": "paragraph"}]}


def tiptap_json_to_markdown(content_json: dict[str, Any] | None) -> str:
    document = normalize_tiptap_document(content_json)
    blocks: list[str] = []
    for node in document.get("content") or []:
        blocks.append(_node_text(node))
    return "\n\n".join(block for block in blocks if block).rstrip("\n")


def _node_text(node: dict[str, Any]) -> str:
    if node.get("type") == "text":
        return str(node.get("text") or "")
    content = node.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(_node_text(child) for child in content if isinstance(child, dict))

