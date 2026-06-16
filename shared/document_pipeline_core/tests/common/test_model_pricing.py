from __future__ import annotations

from document_pipeline_core.common.model_pricing import lookup_openai_model_pricing


def test_openai_model_pricing_has_gpt_5_4_family() -> None:
    nano = lookup_openai_model_pricing("gpt-5.4-nano")
    mini = lookup_openai_model_pricing("gpt-5.4-mini")
    standard = lookup_openai_model_pricing("gpt-5.4")

    assert nano is not None
    assert mini is not None
    assert standard is not None
    assert nano.input_usd_per_million < mini.input_usd_per_million
    assert mini.input_usd_per_million < standard.input_usd_per_million
