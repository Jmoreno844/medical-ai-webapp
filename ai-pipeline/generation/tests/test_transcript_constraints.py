from __future__ import annotations

from common.context_spans import Directive, DirectiveScope
from generation.lib import render_transcript_constraints_block


def test_render_transcript_constraints_block_empty() -> None:
    assert render_transcript_constraints_block([]) == ""


def test_render_transcript_constraints_block_wraps_xml() -> None:
    block = render_transcript_constraints_block(
        [
            Directive(
                scope=DirectiveScope.TRANSCRIPT,
                action="exclude_topic",
                topic="administrativo",
            )
        ]
    )
    assert "<transcript_constraints>" in block
    assert "exclude_topic" in block
