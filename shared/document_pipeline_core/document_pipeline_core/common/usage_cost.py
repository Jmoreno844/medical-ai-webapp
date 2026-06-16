from __future__ import annotations

from dataclasses import dataclass

from document_pipeline_core.common.cost_projection import (
    CostProjectionSettings,
    effective_cached_input_tokens,
    estimate_cacheable_input_tokens,
)
from document_pipeline_core.common.model_pricing import ModelPricing, lookup_model_pricing, normalize_model_id


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class UsageCostLine:
    step: str
    label: str
    cost_bucket: str
    provider: str
    model: str
    usage: TokenUsage
    effective_cached_input_tokens: int
    projected_cacheable_tokens: int
    input_cost_usd: float | None
    output_cost_usd: float | None
    pricing: ModelPricing | None

    @property
    def total_cost_usd(self) -> float | None:
        if self.input_cost_usd is None or self.output_cost_usd is None:
            return None
        return self.input_cost_usd + self.output_cost_usd


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return None


def parse_token_usage(usage: object) -> TokenUsage | None:
    if not isinstance(usage, dict):
        return None

    input_tokens = _coerce_non_negative_int(
        usage.get("input_tokens", usage.get("prompt_tokens"))
    )
    output_tokens = _coerce_non_negative_int(
        usage.get("output_tokens", usage.get("completion_tokens"))
    )
    if input_tokens is None or output_tokens is None:
        return None

    cached_input_tokens = 0
    details = usage.get("input_tokens_details", usage.get("prompt_tokens_details"))
    if isinstance(details, dict):
        cached = _coerce_non_negative_int(details.get("cached_tokens"))
        if cached is None:
            cached = _coerce_non_negative_int(details.get("cached_input_tokens"))
        if cached is not None:
            cached_input_tokens = min(cached, input_tokens)

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )


def compute_usage_cost_usd(
    *,
    provider: str,
    model: str,
    usage: TokenUsage,
    billed_cached_input_tokens: int | None = None,
) -> tuple[float, float, ModelPricing | None]:
    pricing = lookup_model_pricing(provider=provider, model=model)
    if pricing is None:
        return 0.0, 0.0, None

    cached_tokens = (
        usage.cached_input_tokens
        if billed_cached_input_tokens is None
        else min(max(0, billed_cached_input_tokens), usage.input_tokens)
    )
    uncached_input_tokens = max(0, usage.input_tokens - cached_tokens)
    input_cost = (
        uncached_input_tokens / 1_000_000
    ) * pricing.input_usd_per_million + (
        cached_tokens / 1_000_000
    ) * pricing.cached_input_usd_per_million
    output_cost = (usage.output_tokens / 1_000_000) * pricing.output_usd_per_million
    return input_cost, output_cost, pricing


def build_usage_cost_line(
    *,
    step: str,
    label: str,
    provider: str,
    model: str,
    usage: object,
    settings: CostProjectionSettings | None = None,
    result_record: dict[str, object] | None = None,
    cost_bucket: str | None = None,
) -> UsageCostLine | None:
    parsed = parse_token_usage(usage)
    if parsed is None:
        return None

    projection_settings = settings or CostProjectionSettings()
    projected_cacheable_tokens = 0
    if projection_settings.use_cache_pricing and result_record is not None:
        projected_cacheable_tokens = estimate_cacheable_input_tokens(
            step=step,
            label=label,
            result_record=result_record,
            settings=projection_settings,
        )
    billed_cached_tokens = effective_cached_input_tokens(
        parsed,
        projected_cacheable_tokens=projected_cacheable_tokens,
        settings=projection_settings,
    )

    input_cost, output_cost, pricing = compute_usage_cost_usd(
        provider=provider,
        model=model,
        usage=parsed,
        billed_cached_input_tokens=billed_cached_tokens,
    )
    has_pricing = pricing is not None
    return UsageCostLine(
        step=step,
        label=label,
        cost_bucket=cost_bucket or step,
        provider=provider,
        model=normalize_model_id(model),
        usage=parsed,
        effective_cached_input_tokens=billed_cached_tokens,
        projected_cacheable_tokens=projected_cacheable_tokens,
        input_cost_usd=input_cost if has_pricing else None,
        output_cost_usd=output_cost if has_pricing else None,
        pricing=pricing,
    )


def iter_e2e_usage_cost_lines(
    outputs: list[dict[str, object]],
    *,
    settings: CostProjectionSettings | None = None,
) -> list[UsageCostLine]:
    lines: list[UsageCostLine] = []

    for entry in outputs:
        if not isinstance(entry, dict):
            continue
        step = entry.get("step")
        result_record = entry.get("result_record")
        if not isinstance(step, str) or not isinstance(result_record, dict):
            continue

        provider = str(result_record.get("provider", ""))
        model = str(result_record.get("model", ""))

        if step == "filtering":
            line = build_usage_cost_line(
                step=step,
                label="Filtering",
                provider=provider,
                model=model,
                usage=result_record.get("llm_usage"),
                settings=settings,
                result_record=result_record,
            )
            if line is not None:
                lines.append(line)
            continue

        if step == "clustering":
            line = build_usage_cost_line(
                step=step,
                label="Clustering · inicial",
                cost_bucket="clustering_initial",
                provider=provider,
                model=model,
                usage=result_record.get("llm_usage"),
                settings=settings,
                result_record=result_record,
            )
            if line is not None:
                lines.append(line)
            repair_passes = result_record.get("repair_passes")
            if isinstance(repair_passes, list):
                for repair_pass in repair_passes:
                    if not isinstance(repair_pass, dict):
                        continue
                    pass_index = repair_pass.get("pass_index")
                    repair_label = (
                        f"Clustering · repair {pass_index}"
                        if pass_index is not None
                        else "Clustering · repair"
                    )
                    repair_line = build_usage_cost_line(
                        step=step,
                        label=repair_label,
                        cost_bucket="clustering_repair",
                        provider=provider,
                        model=model,
                        usage=repair_pass.get("llm_usage"),
                        settings=settings,
                        result_record=result_record,
                    )
                    if repair_line is not None:
                        lines.append(repair_line)
            continue

        if step == "classification":
            batch_outputs = result_record.get("batch_outputs")
            if not isinstance(batch_outputs, list):
                continue
            for batch in batch_outputs:
                if not isinstance(batch, dict):
                    continue
                batch_index = batch.get("batch_index")
                label = (
                    f"Classification · batch {batch_index}"
                    if batch_index is not None
                    else "Classification · batch"
                )
                line = build_usage_cost_line(
                    step=step,
                    label=label,
                    provider=provider,
                    model=model,
                    usage=batch.get("llm_usage"),
                    settings=settings,
                    result_record=result_record,
                )
                if line is not None:
                    lines.append(line)
            continue

        if step == "generation":
            section_outputs = result_record.get("section_outputs")
            if not isinstance(section_outputs, list):
                continue
            for section in section_outputs:
                if not isinstance(section, dict):
                    continue
                section_id = section.get("section_id")
                label = (
                    f"Generation · {section_id}"
                    if isinstance(section_id, str)
                    else "Generation · section"
                )
                line = build_usage_cost_line(
                    step=step,
                    label=label,
                    provider=provider,
                    model=model,
                    usage=section.get("llm_usage"),
                    settings=settings,
                    result_record=result_record,
                )
                if line is not None:
                    lines.append(line)
            continue

        if step == "context_pipeline":
            llm_calls = result_record.get("llm_calls")
            if not isinstance(llm_calls, list):
                continue
            for call in llm_calls:
                if not isinstance(call, dict):
                    continue
                call_label = call.get("label")
                call_provider = call.get("provider", provider)
                call_model = call.get("model", model)
                if not isinstance(call_label, str):
                    call_label = "Context"
                line = build_usage_cost_line(
                    step=step,
                    label=f"Context · {call_label}",
                    provider=str(call_provider),
                    model=str(call_model),
                    usage=call.get("llm_usage"),
                    settings=settings,
                    result_record=result_record,
                )
                if line is not None:
                    lines.append(line)

    return lines


def summarize_usage_cost_lines(
    lines: list[UsageCostLine],
) -> dict[str, object]:
    total_input_tokens = sum(line.usage.input_tokens for line in lines)
    total_output_tokens = sum(line.usage.output_tokens for line in lines)
    total_cached_tokens = sum(line.effective_cached_input_tokens for line in lines)
    total_reported_cached_tokens = sum(line.usage.cached_input_tokens for line in lines)

    priced_lines = [line for line in lines if line.total_cost_usd is not None]
    total_cost_usd = sum(line.total_cost_usd or 0.0 for line in priced_lines)
    has_unpriced = len(priced_lines) != len(lines)

    by_step: dict[str, float] = {}
    for line in priced_lines:
        if line.total_cost_usd is None:
            continue
        bucket = line.cost_bucket
        by_step[bucket] = by_step.get(bucket, 0.0) + line.total_cost_usd

    return {
        "line_count": len(lines),
        "priced_line_count": len(priced_lines),
        "has_unpriced_lines": has_unpriced,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cached_input_tokens": total_cached_tokens,
        "total_reported_cached_input_tokens": total_reported_cached_tokens,
        "total_cost_usd": total_cost_usd if priced_lines else None,
        "cost_by_step_usd": by_step,
    }


def format_usd(value: float | None, *, multiplier: float = 1.0) -> str:
    if value is None:
        return "—"
    return f"${value * multiplier:.4f}"


__all__ = [
    "CostProjectionSettings",
    "TokenUsage",
    "UsageCostLine",
    "build_usage_cost_line",
    "compute_usage_cost_usd",
    "format_usd",
    "iter_e2e_usage_cost_lines",
    "parse_token_usage",
    "summarize_usage_cost_lines",
]
