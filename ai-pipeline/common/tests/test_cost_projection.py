from __future__ import annotations

from common.cost_projection import (
    CostProjectionSettings,
    effective_cached_input_tokens,
    estimate_cacheable_input_tokens,
)
from common.usage_cost import TokenUsage


def test_effective_cached_uses_max_of_reported_and_projected() -> None:
    usage = TokenUsage(input_tokens=10_000, output_tokens=50, cached_input_tokens=2_000)
    settings = CostProjectionSettings(use_cache_pricing=True)
    assert effective_cached_input_tokens(
        usage,
        projected_cacheable_tokens=5_000,
        settings=settings,
    ) == 5_000
    assert effective_cached_input_tokens(
        usage,
        projected_cacheable_tokens=1_000,
        settings=settings,
    ) == 2_000


def test_estimate_clustering_cache_uses_py_prompt_for_v002() -> None:
    tokens = estimate_cacheable_input_tokens(
        step="clustering",
        label="Clustering",
        result_record={"prompt_version": "v002"},
        settings=CostProjectionSettings(use_cache_pricing=True),
    )
    assert tokens > 0


def test_estimate_clustering_repair_cache_uses_py_prompt_for_v002() -> None:
    tokens = estimate_cacheable_input_tokens(
        step="clustering",
        label="Clustering · repair 1",
        result_record={"repair_prompt_version": "v002"},
        settings=CostProjectionSettings(use_cache_pricing=True),
    )
    assert tokens > 0


def test_estimate_generation_cache_includes_section_when_template_enabled() -> None:
    result_record = {
        "prompt_version": "v001",
        "template_id": "minimal_outpatient_v001",
    }
    with_template = estimate_cacheable_input_tokens(
        step="generation",
        label="Generation · motivo_consulta",
        result_record=result_record,
        settings=CostProjectionSettings(
            use_cache_pricing=True,
            include_template_in_cache=True,
        ),
    )
    without_template = estimate_cacheable_input_tokens(
        step="generation",
        label="Generation · motivo_consulta",
        result_record=result_record,
        settings=CostProjectionSettings(
            use_cache_pricing=True,
            include_template_in_cache=False,
        ),
    )
    assert with_template > without_template
