from __future__ import annotations

from dataclasses import dataclass

PRICING_SOURCE_URL = "https://openai.com/api/pricing/"
PRICING_SOURCE_NOTE = "OpenAI API pricing (standard, <270K context), Jun 2026"

ANTHROPIC_PRICING_SOURCE_URL = (
    "https://platform.claude.com/docs/en/about-claude/models/overview"
)
ANTHROPIC_PRICING_SOURCE_NOTE = (
    "Anthropic Claude API pricing (Haiku 4.5: $1/$5 per MTok, cache read $0.10), Jun 2026"
)


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

# USD per 1M tokens — https://platform.claude.com/docs/en/about-claude/models/overview
_HAIKU_45_PRICING = ModelPricing(
    input_usd_per_million=1.00,
    output_usd_per_million=5.00,
    cached_input_usd_per_million=0.10,
    source=ANTHROPIC_PRICING_SOURCE_NOTE,
)

ANTHROPIC_MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": _HAIKU_45_PRICING,
    "claude-haiku-4-5": _HAIKU_45_PRICING,
}


def normalize_model_id(model: str) -> str:
    return model.strip().lower()


def lookup_openai_model_pricing(model: str) -> ModelPricing | None:
    return OPENAI_MODEL_PRICING.get(normalize_model_id(model))


def lookup_anthropic_model_pricing(model: str) -> ModelPricing | None:
    normalized = normalize_model_id(model)
    direct = ANTHROPIC_MODEL_PRICING.get(normalized)
    if direct is not None:
        return direct
    if normalized.startswith("claude-haiku-4-5"):
        return _HAIKU_45_PRICING
    return None


def lookup_model_pricing(*, provider: str, model: str) -> ModelPricing | None:
    provider_norm = provider.strip().lower()
    if provider_norm == "openai":
        return lookup_openai_model_pricing(model)
    if provider_norm == "anthropic":
        return lookup_anthropic_model_pricing(model)
    return None


__all__ = [
    "ModelPricing",
    "ANTHROPIC_MODEL_PRICING",
    "ANTHROPIC_PRICING_SOURCE_NOTE",
    "ANTHROPIC_PRICING_SOURCE_URL",
    "OPENAI_MODEL_PRICING",
    "PRICING_SOURCE_NOTE",
    "PRICING_SOURCE_URL",
    "lookup_anthropic_model_pricing",
    "lookup_model_pricing",
    "lookup_openai_model_pricing",
    "normalize_model_id",
]
