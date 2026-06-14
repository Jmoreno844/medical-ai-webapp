from __future__ import annotations


def render_block(tag: str, body: str) -> str:
    normalized_tag = tag.strip()
    if not normalized_tag:
        raise ValueError("prompt_block_tag_must_be_non_empty")
    return f"<{normalized_tag}>\n{body.rstrip()}\n</{normalized_tag}>"


def join_blocks(blocks: list[str]) -> str:
    normalized_blocks = [block.strip() for block in blocks if block.strip()]
    return "\n\n".join(normalized_blocks)


__all__ = ["join_blocks", "render_block"]
