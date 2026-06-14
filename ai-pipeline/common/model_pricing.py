from __future__ import annotations

from dataclasses import dataclass

PRICING_SOURCE_URL = "https://openai.com/api/pricing/"
PRICING_SOURCE_NOTE = "OpenAI API pricing (standard, <270K context), Jun 2026"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_million: float
    output_usd_per_million: float
    cached_input_usd_per_million: float
    source: str = PRICING_SOURCE_NOTE


# USD per 1M tokens — https://openai.com/api/pricing/ (+ nano via Azure parity)
OPENAI_MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5.4-nano": ModelPricing(
        input_usd_per_million=0.20,
        output_usd_per_million=1.25,
        cached_input_usd_per_million=0.02,
    ),
    "gpt-5.4-mini": ModelPricing(
        input_usd_per_million=0.75,
        output_usd_per_million=4.50,
        cached_input_usd_per_million=0.075,
    ),
    "gpt-5.4": ModelPricing(
        input_usd_per_million=2.50,
        output_usd_per_million=15.00,
        cached_input_usd_per_million=0.25,
    ),
}


def normalize_model_id(model: str) -> str:
    return model.strip().lower()


def lookup_openai_model_pricing(model: str) -> ModelPricing | None:
    return OPENAI_MODEL_PRICING.get(normalize_model_id(model))


__all__ = [
    "ModelPricing",
    "OPENAI_MODEL_PRICING",
    "PRICING_SOURCE_NOTE",
    "PRICING_SOURCE_URL",
    "lookup_openai_model_pricing",
    "normalize_model_id",
]
