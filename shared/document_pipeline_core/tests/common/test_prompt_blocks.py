from __future__ import annotations

from document_pipeline_core.common.prompt_blocks import join_blocks, render_block


def test_render_block_wraps_body() -> None:
    block = render_block("template_ref", "id: demo")
    assert block == "<template_ref>\nid: demo\n</template_ref>"


def test_join_blocks_separates_with_blank_line() -> None:
    joined = join_blocks(["a", "b"])
    assert joined == "a\n\nb"
