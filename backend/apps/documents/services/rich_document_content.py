from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token

PreferredContentSource = Literal["markdown", "json"]

_MARKDOWN_PARSER = MarkdownIt("commonmark").enable("table")

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
    node_type = normalized.get("type")
    if node_type == "doc":
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
    normalized_markdown = normalize_markdown(markdown)
    if normalized_markdown == "":
        return get_empty_tiptap_doc()

    tokens = _MARKDOWN_PARSER.parse(normalized_markdown)
    content, _ = _parse_block_tokens(tokens, 0, set())
    if not content:
        return get_empty_tiptap_doc()
    return {"type": "doc", "content": content}


def tiptap_json_to_markdown(content_json: dict[str, Any] | None) -> str:
    document = normalize_tiptap_document(content_json)
    content = document.get("content") or []
    if not content:
        return ""
    rendered = _render_block_list(content)
    return rendered.rstrip("\n")


def _parse_block_tokens(
    tokens: list[Token],
    index: int,
    stop_types: set[str],
) -> tuple[list[dict[str, Any]], int]:
    nodes: list[dict[str, Any]] = []

    while index < len(tokens):
        token = tokens[index]
        if token.type in stop_types:
            return nodes, index + 1

        if token.type == "paragraph_open":
            inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
            content = _parse_inline_token(inline_token)
            paragraph: dict[str, Any] = {"type": "paragraph"}
            if content:
                paragraph["content"] = content
            nodes.append(paragraph)
            index += 3
            continue

        if token.type == "heading_open":
            inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
            content = _parse_inline_token(inline_token)
            level = int(token.tag[1]) if token.tag.startswith("h") else 1
            heading: dict[str, Any] = {"type": "heading", "attrs": {"level": level}}
            if content:
                heading["content"] = content
            nodes.append(heading)
            index += 3
            continue

        if token.type == "bullet_list_open":
            content, index = _parse_block_tokens(tokens, index + 1, {"bullet_list_close"})
            nodes.append({"type": "bulletList", "content": content})
            continue

        if token.type == "ordered_list_open":
            attrs: dict[str, Any] = {}
            start = _token_attr(token, "start")
            if start not in (None, "", "1", 1):
                attrs["start"] = int(start)
            content, index = _parse_block_tokens(
                tokens,
                index + 1,
                {"ordered_list_close"},
            )
            ordered_list: dict[str, Any] = {"type": "orderedList", "content": content}
            if attrs:
                ordered_list["attrs"] = attrs
            nodes.append(ordered_list)
            continue

        if token.type == "list_item_open":
            content, index = _parse_block_tokens(tokens, index + 1, {"list_item_close"})
            nodes.append(
                {
                    "type": "listItem",
                    "content": content or [{"type": "paragraph"}],
                }
            )
            continue

        if token.type == "blockquote_open":
            content, index = _parse_block_tokens(tokens, index + 1, {"blockquote_close"})
            nodes.append({"type": "blockquote", "content": content})
            continue

        if token.type in {"fence", "code_block"}:
            attrs: dict[str, Any] = {}
            language = (token.info or "").strip().split(" ", 1)[0]
            if language:
                attrs["language"] = language
            code_block: dict[str, Any] = {"type": "codeBlock"}
            if attrs:
                code_block["attrs"] = attrs
            if token.content:
                code_block["content"] = [{"type": "text", "text": token.content}]
            nodes.append(code_block)
            index += 1
            continue

        if token.type == "table_open":
            table, index = _parse_table(tokens, index)
            nodes.append(table)
            continue

        if token.type == "hr":
            nodes.append({"type": "horizontalRule"})
            index += 1
            continue

        if token.type == "inline":
            content = _parse_inline_token(token)
            paragraph: dict[str, Any] = {"type": "paragraph"}
            if content:
                paragraph["content"] = content
            nodes.append(paragraph)
            index += 1
            continue

        index += 1

    return nodes, index


def _parse_table(
    tokens: list[Token],
    index: int,
) -> tuple[dict[str, Any], int]:
    rows: list[dict[str, Any]] = []
    index += 1

    while index < len(tokens):
        token = tokens[index]
        if token.type == "table_close":
            return {"type": "table", "content": rows}, index + 1
        if token.type == "tr_open":
            row, index = _parse_table_row(tokens, index)
            rows.append(row)
            continue
        index += 1

    return {"type": "table", "content": rows}, index


def _parse_table_row(
    tokens: list[Token],
    index: int,
) -> tuple[dict[str, Any], int]:
    cells: list[dict[str, Any]] = []
    index += 1

    while index < len(tokens):
        token = tokens[index]
        if token.type == "tr_close":
            return {"type": "tableRow", "content": cells}, index + 1

        if token.type in {"th_open", "td_open"}:
            cell_type = "tableHeader" if token.type == "th_open" else "tableCell"
            cell_content: list[dict[str, Any]] = []
            index += 1
            while index < len(tokens) and tokens[index].type not in {"th_close", "td_close"}:
                cell_token = tokens[index]
                if cell_token.type == "inline":
                    inline_content = _parse_inline_token(cell_token)
                    paragraph: dict[str, Any] = {"type": "paragraph"}
                    if inline_content:
                        paragraph["content"] = inline_content
                    cell_content.append(paragraph)
                index += 1
            if not cell_content:
                cell_content.append({"type": "paragraph"})
            cells.append({"type": cell_type, "content": cell_content})
            if index < len(tokens):
                index += 1
            continue

        index += 1

    return {"type": "tableRow", "content": cells}, index


def _parse_inline_token(inline_token: Token | None) -> list[dict[str, Any]]:
    children = inline_token.children if inline_token and inline_token.children else []
    nodes, _ = _parse_inline_children(children, 0, set(), [])
    return nodes


def _parse_inline_children(
    tokens: list[Token],
    index: int,
    stop_types: set[str],
    active_marks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    nodes: list[dict[str, Any]] = []

    while index < len(tokens):
        token = tokens[index]
        if token.type in stop_types:
            return nodes, index + 1

        if token.type == "text":
            if token.content:
                text_node: dict[str, Any] = {"type": "text", "text": token.content}
                if active_marks:
                    text_node["marks"] = deepcopy(active_marks)
                nodes.append(text_node)
            index += 1
            continue

        if token.type == "code_inline":
            text_node = {"type": "text", "text": token.content}
            marks = [*active_marks, {"type": "code"}]
            text_node["marks"] = deepcopy(marks)
            nodes.append(text_node)
            index += 1
            continue

        if token.type in {"softbreak", "hardbreak"}:
            nodes.append({"type": "hardBreak"})
            index += 1
            continue

        if token.type == "image":
            alt_text = token.content or _token_attr(token, "title") or ""
            if alt_text:
                text_node = {"type": "text", "text": alt_text}
                if active_marks:
                    text_node["marks"] = deepcopy(active_marks)
                nodes.append(text_node)
            index += 1
            continue

        mark = _mark_from_inline_token(token)
        if mark is not None and token.nesting == 1:
            close_type = token.type.replace("_open", "_close")
            nested_nodes, index = _parse_inline_children(
                tokens,
                index + 1,
                {close_type},
                [*active_marks, mark],
            )
            nodes.extend(nested_nodes)
            continue

        index += 1

    return nodes, index


def _mark_from_inline_token(token: Token) -> dict[str, Any] | None:
    if token.type == "strong_open":
        return {"type": "bold"}
    if token.type == "em_open":
        return {"type": "italic"}
    if token.type == "s_open":
        return {"type": "strike"}
    if token.type == "link_open":
        href = _token_attr(token, "href")
        attrs = {"href": href or ""}
        title = _token_attr(token, "title")
        if title:
            attrs["title"] = title
        return {"type": "link", "attrs": attrs}
    return None


def _token_attr(token: Token, key: str) -> Any:
    attrs = getattr(token, "attrs", None)
    if attrs is None:
        return None
    if isinstance(attrs, dict):
        return attrs.get(key)
    if isinstance(attrs, list):
        for attr_key, attr_value in attrs:
            if attr_key == key:
                return attr_value
    return None


def _render_block_list(nodes: list[dict[str, Any]]) -> str:
    rendered_blocks: list[str] = []
    for node in nodes:
        rendered = _render_block(node).rstrip("\n")
        if rendered.strip() == "":
            continue
        rendered_blocks.append(rendered)
    return "\n\n".join(rendered_blocks)


def _render_block(node: dict[str, Any]) -> str:
    node_type = node.get("type")

    if node_type == "paragraph":
        return _render_inline_nodes(node.get("content") or [])

    if node_type == "heading":
        level = int((node.get("attrs") or {}).get("level") or 1)
        return f"{'#' * max(level, 1)} {_render_inline_nodes(node.get('content') or [])}".rstrip()

    if node_type == "bulletList":
        return _render_list(node.get("content") or [], ordered=False, start=1)

    if node_type == "orderedList":
        start = int((node.get("attrs") or {}).get("start") or 1)
        return _render_list(node.get("content") or [], ordered=True, start=start)

    if node_type == "blockquote":
        child = _render_block_list(node.get("content") or [])
        if child == "":
            return "> "
        return "\n".join(
            f"> {line}" if line else ">"
            for line in child.splitlines()
        )

    if node_type == "codeBlock":
        language = (node.get("attrs") or {}).get("language") or ""
        text = "".join(
            child.get("text", "")
            for child in node.get("content") or []
            if child.get("type") == "text"
        )
        return f"```{language}\n{text}\n```"

    if node_type == "horizontalRule":
        return "---"

    if node_type == "table":
        return _render_table(node)

    return ""


def _render_list(
    items: list[dict[str, Any]],
    *,
    ordered: bool,
    start: int,
) -> str:
    lines: list[str] = []
    counter = start
    for item in items:
        marker = f"{counter}." if ordered else "-"
        lines.append(_render_list_item(item, marker))
        if ordered:
            counter += 1
    return "\n".join(lines)


def _render_list_item(node: dict[str, Any], marker: str) -> str:
    blocks = node.get("content") or [{"type": "paragraph"}]
    prefix = f"{marker} "
    continuation = " " * len(prefix)
    lines: list[str] = []

    for block_index, block in enumerate(blocks):
        rendered_block = _render_block(block)
        if rendered_block == "":
            if block_index == 0:
                lines.append(prefix.rstrip())
            continue

        block_lines = rendered_block.splitlines() or [""]
        if block_index == 0:
            lines.append(f"{prefix}{block_lines[0]}".rstrip())
            for extra_line in block_lines[1:]:
                lines.append(f"{continuation}{extra_line}".rstrip())
            continue

        for extra_line in block_lines:
            lines.append(f"{continuation}{extra_line}".rstrip())

    return "\n".join(lines)


def _render_table(node: dict[str, Any]) -> str:
    rows = node.get("content") or []
    if not rows:
        return ""

    rendered_rows: list[list[str]] = []
    for row in rows:
        rendered_rows.append(
            [_render_table_cell(cell) for cell in row.get("content") or []]
        )

    header = rendered_rows[0]
    separator = ["---"] * len(header)
    body = rendered_rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _render_table_cell(node: dict[str, Any]) -> str:
    blocks = node.get("content") or []
    pieces: list[str] = []
    for block in blocks:
        if block.get("type") == "paragraph":
            pieces.append(_render_inline_nodes(block.get("content") or []))
        else:
            pieces.append(_render_block(block))
    return " ".join(piece.replace("\n", " ").strip() for piece in pieces if piece).replace("|", "\\|")


def _render_inline_nodes(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "hardBreak":
            parts.append("  \n")
            continue
        if node_type != "text":
            continue

        text = node.get("text", "")
        parts.append(_apply_marks(text, node.get("marks") or []))
    return "".join(parts)


def _apply_marks(text: str, marks: list[dict[str, Any]]) -> str:
    if not marks:
        return text

    ordered_marks = sorted(
        marks,
        key=lambda mark: {
            "code": 0,
            "italic": 1,
            "bold": 2,
            "strike": 3,
            "link": 4,
        }.get(mark.get("type", ""), 99),
    )
    rendered = text
    for mark in ordered_marks:
        mark_type = mark.get("type")
        if mark_type == "code":
            rendered = f"`{rendered}`"
            continue
        if mark_type == "italic":
            rendered = f"*{rendered}*"
            continue
        if mark_type == "bold":
            rendered = f"**{rendered}**"
            continue
        if mark_type == "strike":
            rendered = f"~~{rendered}~~"
            continue
        if mark_type == "link":
            attrs = mark.get("attrs") or {}
            href = attrs.get("href") or ""
            title = attrs.get("title")
            title_suffix = f' "{title}"' if title else ""
            rendered = f"[{rendered}]({href}{title_suffix})"
    return rendered
