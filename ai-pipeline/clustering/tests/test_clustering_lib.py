from __future__ import annotations

from clustering.lib import (
    format_clustering_output_for_detail,
    format_clustering_repair_pass_for_detail,
)


def test_format_clustering_output_for_detail_compact_keeps_thinking_text() -> None:
    compact = format_clustering_output_for_detail(
        {
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "thinking": "razonamiento interno",
            "thinking_source": "openai.responses.reasoning.summary",
            "llm_usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 8},
            },
            "repair_passes": [
                {
                    "pass_index": 1,
                    "thinking": "repair thinking",
                    "thinking_source": "message.reasoning",
                    "llm_usage": {"input_tokens": 10, "output_tokens": 5},
                }
            ],
        },
        "compact",
    )
    assert compact["thinking"] == "razonamiento interno"
    assert compact["thinking_chars"] == len("razonamiento interno")
    assert compact["thinking_source"] == "openai.responses.reasoning.summary"
    repair_pass = compact["repair_passes"][0]
    assert isinstance(repair_pass, dict)
    assert repair_pass["thinking"] == "repair thinking"
    assert repair_pass["thinking_chars"] == len("repair thinking")


def test_format_clustering_repair_pass_for_detail_full_keeps_thinking() -> None:
    repair_pass = format_clustering_repair_pass_for_detail(
        {
            "pass_index": 1,
            "thinking": "repair thinking",
            "thinking_source": "message.reasoning",
        },
        "full",
    )
    assert repair_pass["thinking"] == "repair thinking"
