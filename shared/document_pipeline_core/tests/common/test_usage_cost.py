from __future__ import annotations

from document_pipeline_core.common.cost_projection import (
    CostProjectionSettings,
    effective_cached_input_tokens,
    estimate_cacheable_input_tokens,
)
from document_pipeline_core.common.usage_cost import (
    TokenUsage,
    build_usage_cost_line,
    compute_usage_cost_usd,
    iter_e2e_usage_cost_lines,
    parse_token_usage,
    summarize_usage_cost_lines,
)


def test_parse_token_usage_openai_responses_format() -> None:
    usage = parse_token_usage(
        {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_tokens_details": {"cached_tokens": 100},
        }
    )
    assert usage == TokenUsage(
        input_tokens=1000,
        output_tokens=200,
        cached_input_tokens=100,
    )


def test_compute_usage_cost_usd_gpt_5_4_mini() -> None:
    input_cost, output_cost, pricing = compute_usage_cost_usd(
        provider="openai",
        model="gpt-5.4-mini",
        usage=TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000),
    )
    assert pricing is not None
    assert input_cost == 0.75
    assert output_cost == 4.50


def test_compute_usage_cost_usd_claude_haiku_4_5() -> None:
    input_cost, output_cost, pricing = compute_usage_cost_usd(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        usage=TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000),
    )
    assert pricing is not None
    assert input_cost == 1.00
    assert output_cost == 5.00


def test_compute_usage_cost_usd_claude_haiku_cache_read() -> None:
    input_cost, _, pricing = compute_usage_cost_usd(
        provider="anthropic",
        model="claude-haiku-4-5",
        usage=TokenUsage(
            input_tokens=1_000_000,
            output_tokens=0,
            cached_input_tokens=1_000_000,
        ),
        billed_cached_input_tokens=1_000_000,
    )
    assert pricing is not None
    assert input_cost == 0.10


def test_compute_usage_cost_usd_no_cache_mode_ignores_reported_cached() -> None:
    input_cost, _, pricing = compute_usage_cost_usd(
        provider="openai",
        model="gpt-5.4-mini",
        usage=TokenUsage(
            input_tokens=1_000_000,
            output_tokens=0,
            cached_input_tokens=500_000,
        ),
        billed_cached_input_tokens=0,
    )
    assert pricing is not None
    assert input_cost == 0.75


def test_effective_cached_input_tokens_projection() -> None:
    usage = TokenUsage(input_tokens=10_000, output_tokens=100, cached_input_tokens=0)
    settings = CostProjectionSettings(use_cache_pricing=True)
    assert effective_cached_input_tokens(
        usage,
        projected_cacheable_tokens=3_000,
        settings=settings,
    ) == 3_000
    assert effective_cached_input_tokens(
        usage,
        projected_cacheable_tokens=3_000,
        settings=CostProjectionSettings(use_cache_pricing=False),
    ) == 0


def test_build_usage_cost_line_cache_projection_lowers_input_cost() -> None:
    no_cache = build_usage_cost_line(
        step="filtering",
        label="Filtering",
        provider="openai",
        model="gpt-5.4-mini",
        usage={"input_tokens": 20_000, "output_tokens": 500},
        settings=CostProjectionSettings(use_cache_pricing=False),
        result_record={"prompt_version": "v001"},
    )
    with_cache = build_usage_cost_line(
        step="filtering",
        label="Filtering",
        provider="openai",
        model="gpt-5.4-mini",
        usage={"input_tokens": 20_000, "output_tokens": 500},
        settings=CostProjectionSettings(use_cache_pricing=True),
        result_record={"prompt_version": "v001"},
    )
    assert no_cache is not None
    assert with_cache is not None
    assert with_cache.projected_cacheable_tokens > 0
    assert with_cache.effective_cached_input_tokens == with_cache.projected_cacheable_tokens
    assert with_cache.input_cost_usd is not None
    assert no_cache.input_cost_usd is not None
    assert with_cache.input_cost_usd < no_cache.input_cost_usd


def test_estimate_cacheable_tokens_classification_template_toggle() -> None:
    result_record = {
        "prompt_version": "v003",
        "template_id": "consulta_estructurada_v001",
    }
    with_template = estimate_cacheable_input_tokens(
        step="classification",
        label="Classification · batch 1",
        result_record=result_record,
        settings=CostProjectionSettings(
            use_cache_pricing=True,
            include_template_in_cache=True,
        ),
    )
    without_template = estimate_cacheable_input_tokens(
        step="classification",
        label="Classification · batch 1",
        result_record=result_record,
        settings=CostProjectionSettings(
            use_cache_pricing=True,
            include_template_in_cache=False,
        ),
    )
    assert with_template > without_template
    assert without_template > 0


def test_iter_e2e_usage_cost_lines_splits_clustering_initial_and_repair() -> None:
    outputs = [
        {
            "step": "clustering",
            "result_record": {
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "prompt_version": "v001",
                "llm_usage": {"input_tokens": 1000, "output_tokens": 100},
                "repair_passes": [
                    {
                        "pass_index": 1,
                        "llm_usage": {"input_tokens": 200, "output_tokens": 20},
                    }
                ],
            },
        },
    ]

    lines = iter_e2e_usage_cost_lines(outputs)
    assert len(lines) == 2
    assert lines[0].label == "Clustering · inicial"
    assert lines[0].cost_bucket == "clustering_initial"
    assert lines[1].label == "Clustering · repair 1"
    assert lines[1].cost_bucket == "clustering_repair"

    summary = summarize_usage_cost_lines(lines)
    cost_by_step = summary["cost_by_step_usd"]
    assert isinstance(cost_by_step, dict)
    assert "clustering_initial" in cost_by_step
    assert "clustering_repair" in cost_by_step
    assert "clustering" not in cost_by_step


def test_iter_e2e_usage_cost_lines_aggregates_generation_sections() -> None:
    outputs = [
        {
            "step": "filtering",
            "result_record": {
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "llm_usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                },
            },
        },
        {
            "step": "generation",
            "result_record": {
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "section_outputs": [
                    {
                        "section_id": "motivo_consulta",
                        "llm_usage": {
                            "input_tokens": 200,
                            "output_tokens": 20,
                        },
                    },
                    {
                        "section_id": "plan",
                        "llm_usage": {
                            "input_tokens": 300,
                            "output_tokens": 30,
                        },
                    },
                ],
            },
        },
    ]

    lines = iter_e2e_usage_cost_lines(outputs)
    assert len(lines) == 3
    summary = summarize_usage_cost_lines(lines)
    assert summary["total_input_tokens"] == 600
    assert summary["total_output_tokens"] == 60
    assert isinstance(summary["total_cost_usd"], float)
    assert summary["total_cost_usd"] > 0
