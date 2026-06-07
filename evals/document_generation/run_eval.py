from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import time

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = PROJECT_ROOT / "document_generation_worker"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app.llm import stream_document_generation  # noqa: E402
from app.settings import Settings  # noqa: E402
from evals.document_generation.lib import (  # noqa: E402
    DEFAULT_TEMPLATE_FILE,
    EVALS_ROOT,
    JUDGE_SCORE_DIMENSIONS,
    ANTHROPIC_THINKING_BUDGET_MIN_TOKENS,
    EvalCase,
    GenerationMetrics,
    JudgeResult,
    JudgeSpec,
    ModelSpec,
    RunScoreSummary,
    build_run_score_summaries,
    estimate_generation_cost_usd,
    load_cases,
    load_judge_prompt,
    load_prompt_version,
    parse_judge_response,
    parse_model_specs,
    render_generation_prompt,
    render_judge_prompt,
    resolve_template_file,
    select_cases,
)


DEFAULT_CASES_PATH = EVALS_ROOT / "cases.json"
DEFAULT_RESULTS_DIR = EVALS_ROOT / "results"
DEFAULT_PROMPT_VERSION = "document_generation_v002"
DEFAULT_JUDGE_PROMPT_VERSION = "clinical_document_judge_v002"
DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_JUDGE_MODEL = "gpt-5.4"
DEFAULT_ANTHROPIC_JUDGE_MODEL = "claude-opus-4-8"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
OPENAI_DOCUMENT_GENERATION_TEMPERATURE = 0.0
OPENAI_DOCUMENT_GENERATION_REASONING_EFFORT = "none"
OPENAI_REASONING_EFFORT_CHOICES = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)
OPENAI_JUDGE_REASONING_EFFORT = "high"
ANTHROPIC_JUDGE_MAX_TOKENS = 4096
ANTHROPIC_JUDGE_REPAIR_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    openai_reasoning_effort: str
    anthropic_thinking_budget_tokens: int | None


@dataclass(frozen=True, slots=True)
class GenerationTokenUsage:
    input_tokens: int
    output_tokens: int
    thinking_tokens: int


@dataclass(frozen=True, slots=True)
class DocumentGenerationResult:
    generated_document: str
    generation_reasoning: str | None
    token_usage: GenerationTokenUsage | None
    first_token_at: float | None


ANTHROPIC_EVAL_MAX_OUTPUT_TOKENS = 64000
ANTHROPIC_GENERATION_TEMPERATURE = 0.0
ANTHROPIC_THINKING_TEMPERATURE = 1.0


def _env_or_default(name: str, fallback: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or fallback


def _parse_optional_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return None if value <= 0 else value
    normalized = str(value).strip()
    if not normalized:
        return None
    parsed = int(normalized)
    return None if parsed <= 0 else parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local evals for clinical document generation models."
    )
    parser.add_argument(
        "--cases",
        default=os.environ.get("EVAL_CASES_FILE", str(DEFAULT_CASES_PATH)),
    )
    parser.add_argument(
        "--prompt-version",
        default=_env_or_default("PROMPT_VERSION", DEFAULT_PROMPT_VERSION),
    )
    parser.add_argument(
        "--models",
        default=os.environ.get(
            "MODELS",
            ",".join(
                [
                    f"gemini:{_env_or_default('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}",
                    (
                        f"anthropic:{_env_or_default('ANTHROPIC_MODEL', DEFAULT_ANTHROPIC_MODEL)}"
                    ),
                ]
            ),
        ),
        help="Comma-separated list like gemini:model,anthropic:model,openai:model",
    )
    parser.add_argument(
        "--judge-provider",
        default=_env_or_default("JUDGE_PROVIDER", DEFAULT_JUDGE_PROVIDER),
    )
    parser.add_argument(
        "--judge-model",
        default=_env_or_default("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    )
    parser.add_argument(
        "--judge-prompt-version",
        default=_env_or_default(
            "JUDGE_PROMPT_VERSION",
            DEFAULT_JUDGE_PROMPT_VERSION,
        ),
    )
    parser.add_argument(
        "--judges",
        default=os.environ.get("JUDGES", "").strip() or None,
        help=(
            "Comma-separated list like openai:gpt-5.4,anthropic:claude-opus-4-8. "
            "If omitted, falls back to --judge-provider/--judge-model."
        ),
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", str(DEFAULT_RESULTS_DIR)),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.environ["COUNT"]) if os.environ.get("COUNT") else None,
    )
    parser.add_argument(
        "--last",
        type=int,
        default=int(os.environ["LAST"]) if os.environ.get("LAST") else None,
        help="Select the last N cases from the cases file. Mutually exclusive with --count.",
    )
    parser.add_argument(
        "--case-id",
        default=os.environ.get("CASE_ID") or None,
    )
    parser.add_argument(
        "--template-file",
        default=_env_or_default("TEMPLATE", DEFAULT_TEMPLATE_FILE),
        help=(
            "Clinical template for all cases. Path relative to "
            "evals/document_generation/, e.g. "
            "templates/clinical_document_template_v004.md"
        ),
    )
    parser.add_argument(
        "--openai-reasoning-effort",
        default=_env_or_default(
            "OPENAI_REASONING_EFFORT",
            OPENAI_DOCUMENT_GENERATION_REASONING_EFFORT,
        ),
        choices=OPENAI_REASONING_EFFORT_CHOICES,
        help=(
            "OpenAI generation reasoning effort. Default none (no thinking tokens). "
            "Supported values include high and xhigh on gpt-5.4-mini."
        ),
    )
    parser.add_argument(
        "--anthropic-thinking-budget",
        default=_parse_optional_int(os.environ.get("ANTHROPIC_THINKING_BUDGET")),
        type=_parse_optional_int,
        help=(
            "Anthropic extended-thinking budget in tokens for Haiku generation. "
            "Omit or set 0 to disable (default). Minimum 1024 when enabled."
        ),
    )
    args = parser.parse_args()
    if args.count is not None and args.last is not None:
        parser.error("--count and --last cannot be used together")
    return args


def build_settings(provider: str, model: str) -> Settings:
    env_file = WORKER_ROOT / ".env.local"
    return Settings(
        _env_file=str(env_file),
        DOCUMENT_GENERATION_PROVIDER=provider,
        DOCUMENT_GENERATION_MODEL=model,
    )


def build_generation_config(args: argparse.Namespace) -> GenerationConfig:
    thinking_budget = args.anthropic_thinking_budget
    if (
        thinking_budget is not None
        and thinking_budget < ANTHROPIC_THINKING_BUDGET_MIN_TOKENS
    ):
        raise ValueError(
            "anthropic_thinking_budget_must_be_at_least_"
            f"{ANTHROPIC_THINKING_BUDGET_MIN_TOKENS}_or_disabled"
        )
    return GenerationConfig(
        openai_reasoning_effort=args.openai_reasoning_effort.strip().lower(),
        anthropic_thinking_budget_tokens=thinking_budget,
    )


def _openai_generation_uses_reasoning_effort(reasoning_effort: str) -> bool:
    return reasoning_effort != "none"


def _build_generation_metrics(
    *,
    model: str,
    started_at: float,
    first_token_at: float,
    finished_at: float,
    token_usage: GenerationTokenUsage | None,
    generation_config: GenerationConfig,
) -> GenerationMetrics:
    estimated_cost_usd: float | None = None
    cost_breakdown: dict[str, float] | None = None
    if token_usage is not None:
        cost_estimate = estimate_generation_cost_usd(
            model=model,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            thinking_tokens=token_usage.thinking_tokens,
        )
        if cost_estimate is not None:
            estimated_cost_usd, cost_breakdown = cost_estimate

    return GenerationMetrics(
        time_to_first_token_ms=int((first_token_at - started_at) * 1000),
        time_after_first_token_ms=int((finished_at - first_token_at) * 1000),
        total_generation_ms=int((finished_at - started_at) * 1000),
        input_tokens=token_usage.input_tokens if token_usage else None,
        output_tokens=token_usage.output_tokens if token_usage else None,
        thinking_tokens=token_usage.thinking_tokens if token_usage else None,
        estimated_cost_usd=estimated_cost_usd,
        cost_breakdown=cost_breakdown,
        openai_reasoning_effort=generation_config.openai_reasoning_effort,
        anthropic_thinking_budget_tokens=(
            generation_config.anthropic_thinking_budget_tokens
        ),
    )


def _get_openai_judge_reasoning_effort(judge_model: str) -> str | None:
    normalized_model = judge_model.strip().lower()
    if normalized_model == "gpt-5.4" or normalized_model.startswith("gpt-5.4-"):
        return OPENAI_JUDGE_REASONING_EFFORT
    return None


def _build_anthropic_judge_repair_message(
    *,
    parse_error: str,
    previous_raw: str,
) -> str:
    return (
        "Tu respuesta anterior no cumplio el esquema JSON requerido. "
        f"Error de validacion: {parse_error}. "
        "Devuelve de nuevo TODO el objeto JSON completo, valido, sin markdown y "
        "sin texto adicional. Debes incluir exactamente estas llaves: "
        "clinical_safety_score, faithfulness_score, template_adherence_score, "
        "uncertainty_handling_score, invented_info, missing_info, "
        "contradiction_info, dosing_error_info, verdict, summary. "
        "Si una lista esta vacia, devuelvela como []. "
        "Respuesta anterior:\n"
        f"{previous_raw}"
    )


def parse_judge_specs(
    raw: str | None,
    *,
    default_provider: str,
    default_model: str,
) -> list[JudgeSpec]:
    if not raw:
        return [
            JudgeSpec(
                alias=default_provider.strip().lower(),
                provider=default_provider.strip().lower(),
                model=default_model.strip(),
            )
        ]

    provider_aliases = {
        "openai": "openai",
        "gpt": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
    }
    specs: list[JudgeSpec] = []
    seen_aliases: dict[str, int] = {}
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        provider_part, sep, model_part = normalized.partition(":")
        if not sep:
            raise ValueError(
                "Invalid judge spec. Expected provider:model, "
                f"got {normalized!r}"
            )
        provider_key = provider_part.strip().lower()
        provider = provider_aliases.get(provider_key)
        if provider is None:
            raise ValueError(f"Unsupported judge provider: {provider_part}")
        model = model_part.strip()
        if not model:
            raise ValueError(f"Judge model missing in spec: {normalized!r}")
        alias_count = seen_aliases.get(provider, 0) + 1
        seen_aliases[provider] = alias_count
        alias = provider if alias_count == 1 else f"{provider}{alias_count}"
        specs.append(JudgeSpec(alias=alias, provider=provider, model=model))
    if not specs:
        raise ValueError("At least one judge spec is required")
    return specs


def _extract_anthropic_reasoning(final_message: object) -> str | None:
    thinking_parts: list[str] = []
    for block in getattr(final_message, "content", []) or []:
        thinking = getattr(block, "thinking", None)
        if isinstance(thinking, str) and thinking.strip():
            thinking_parts.append(thinking.strip())
    if not thinking_parts:
        return None
    return "\n\n".join(thinking_parts)


def _build_openai_token_usage(usage: object) -> GenerationTokenUsage:
    thinking_tokens = 0
    completion_tokens = getattr(usage, "completion_tokens", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    if completion_details is not None:
        reasoning_tokens = getattr(completion_details, "reasoning_tokens", None)
        if isinstance(reasoning_tokens, int):
            thinking_tokens = reasoning_tokens

    if completion_tokens is None and hasattr(usage, "output_tokens"):
        output_tokens_total = getattr(usage, "output_tokens", 0) or 0
        output_details = getattr(usage, "output_tokens_details", None)
        if output_details is not None:
            reasoning_tokens = getattr(output_details, "reasoning_tokens", None)
            if isinstance(reasoning_tokens, int):
                thinking_tokens = reasoning_tokens
        return GenerationTokenUsage(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=max(output_tokens_total - thinking_tokens, 0),
            thinking_tokens=thinking_tokens,
        )

    completion_total = completion_tokens or 0
    return GenerationTokenUsage(
        input_tokens=prompt_tokens or 0,
        output_tokens=max(completion_total - thinking_tokens, 0),
        thinking_tokens=thinking_tokens,
    )


async def _generate_with_anthropic_api(
    *,
    prompt: str,
    model: str,
    generation_config: GenerationConfig,
) -> DocumentGenerationResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic API evals")

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    thinking_budget = generation_config.anthropic_thinking_budget_tokens
    request_kwargs: dict[str, object] = {
        "model": model,
        "max_tokens": ANTHROPIC_EVAL_MAX_OUTPUT_TOKENS,
        "temperature": (
            ANTHROPIC_THINKING_TEMPERATURE
            if thinking_budget is not None
            else ANTHROPIC_GENERATION_TEMPERATURE
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    if thinking_budget is not None:
        request_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    first_token_at: float | None = None
    async with client.messages.stream(**request_kwargs) as stream:
        chunks: list[str] = []
        async for text in stream.text_stream:
            if text:
                if first_token_at is None:
                    first_token_at = time.monotonic()
                chunks.append(text)
        final_message = await stream.get_final_message()

    usage = final_message.usage
    thinking_tokens = 0
    if usage.output_tokens_details is not None:
        thinking_tokens = usage.output_tokens_details.thinking_tokens
    output_tokens = max(usage.output_tokens - thinking_tokens, 0)
    return DocumentGenerationResult(
        generated_document="".join(chunks).strip(),
        generation_reasoning=_extract_anthropic_reasoning(final_message),
        token_usage=GenerationTokenUsage(
            input_tokens=usage.input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
        ),
        first_token_at=first_token_at,
    )


async def _generate_with_openai_chat_api(
    *,
    prompt: str,
    model: str,
    generation_config: GenerationConfig,
) -> DocumentGenerationResult:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI generation evals")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    request: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": OPENAI_DOCUMENT_GENERATION_TEMPERATURE,
        "reasoning_effort": generation_config.openai_reasoning_effort,
    }

    stream = await client.chat.completions.create(**request)
    chunks: list[str] = []
    token_usage: GenerationTokenUsage | None = None
    first_token_at: float | None = None
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                if first_token_at is None:
                    first_token_at = time.monotonic()
                chunks.append(delta)
        if chunk.usage is None:
            continue
        token_usage = _build_openai_token_usage(chunk.usage)

    return DocumentGenerationResult(
        generated_document="".join(chunks).strip(),
        generation_reasoning=None,
        token_usage=token_usage,
        first_token_at=first_token_at,
    )


async def _generate_with_openai_responses_api(
    *,
    prompt: str,
    model: str,
    generation_config: GenerationConfig,
) -> DocumentGenerationResult:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI generation evals")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    stream = await client.responses.create(
        model=model,
        input=prompt,
        stream=True,
        reasoning={
            "effort": generation_config.openai_reasoning_effort,
            "summary": "detailed",
        },
    )

    document_parts: list[str] = []
    reasoning_parts: list[str] = []
    reasoning_summary_parts: list[str] = []
    token_usage: GenerationTokenUsage | None = None
    first_token_at: float | None = None
    async for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "") or ""
            if delta:
                if first_token_at is None:
                    first_token_at = time.monotonic()
                document_parts.append(delta)
            continue
        if event_type == "response.reasoning_text.delta":
            delta = getattr(event, "delta", "") or ""
            if delta:
                reasoning_parts.append(delta)
            continue
        if event_type == "response.reasoning_summary_text.delta":
            delta = getattr(event, "delta", "") or ""
            if delta:
                reasoning_summary_parts.append(delta)
            continue
        if event_type != "response.completed":
            continue
        response = getattr(event, "response", None)
        if response is not None and getattr(response, "usage", None) is not None:
            token_usage = _build_openai_token_usage(response.usage)

    generation_reasoning = "".join(reasoning_parts).strip()
    if not generation_reasoning:
        generation_reasoning = "".join(reasoning_summary_parts).strip() or None

    return DocumentGenerationResult(
        generated_document="".join(document_parts).strip(),
        generation_reasoning=generation_reasoning,
        token_usage=token_usage,
        first_token_at=first_token_at,
    )


async def _generate_with_openai_api(
    *,
    prompt: str,
    model: str,
    generation_config: GenerationConfig,
) -> DocumentGenerationResult:
    if _openai_generation_uses_reasoning_effort(
        generation_config.openai_reasoning_effort
    ):
        return await _generate_with_openai_responses_api(
            prompt=prompt,
            model=model,
            generation_config=generation_config,
        )
    return await _generate_with_openai_chat_api(
        prompt=prompt,
        model=model,
        generation_config=generation_config,
    )


async def generate_document(
    case: EvalCase,
    spec: ModelSpec,
    prompt_version: str,
    generation_config: GenerationConfig,
) -> tuple[str, str | None, GenerationMetrics]:
    prompt_template = load_prompt_version(prompt_version)
    prompt = render_generation_prompt(prompt_template, case)
    settings = build_settings(spec.provider, spec.model)
    started_at = time.monotonic()
    generation_result: DocumentGenerationResult

    if spec.provider == "anthropic_api":
        generation_result = await _generate_with_anthropic_api(
            prompt=prompt,
            model=spec.model,
            generation_config=generation_config,
        )
    elif spec.provider == "openai_api":
        generation_result = await _generate_with_openai_api(
            prompt=prompt,
            model=spec.model,
            generation_config=generation_config,
        )
    else:
        chunks: list[str] = []
        first_token_at: float | None = None
        chunk_iter = stream_document_generation(prompt=prompt, settings=settings)
        async for chunk in chunk_iter:
            if first_token_at is None:
                first_token_at = time.monotonic()
            chunks.append(chunk)
        generation_result = DocumentGenerationResult(
            generated_document="".join(chunks).strip(),
            generation_reasoning=None,
            token_usage=None,
            first_token_at=first_token_at,
        )

    finished_at = time.monotonic()
    first_token_at = generation_result.first_token_at
    if first_token_at is None:
        first_token_at = finished_at

    metrics = _build_generation_metrics(
        model=spec.model,
        started_at=started_at,
        first_token_at=first_token_at,
        finished_at=finished_at,
        token_usage=generation_result.token_usage,
        generation_config=generation_config,
    )
    return (
        generation_result.generated_document,
        generation_result.generation_reasoning,
        metrics,
    )


async def judge_document(
    *,
    case: EvalCase,
    generated_document: str,
    judge_provider: str,
    judge_model: str,
    judge_prompt_version: str,
) -> tuple[JudgeResult, str]:
    normalized_provider = judge_provider.strip().lower()
    if normalized_provider == "openai":
        return await _judge_document_openai(
            case=case,
            generated_document=generated_document,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
        )
    if normalized_provider == "anthropic":
        return await _judge_document_anthropic(
            case=case,
            generated_document=generated_document,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
        )
    raise ValueError(f"Unsupported judge provider: {judge_provider}")


async def _judge_document_openai(
    *,
    case: EvalCase,
    generated_document: str,
    judge_model: str,
    judge_prompt_version: str,
) -> tuple[JudgeResult, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI judge evals")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    judge_template = load_judge_prompt(judge_prompt_version)
    prompt = render_judge_prompt(
        judge_template,
        case=case,
        generated_document=generated_document,
    )
    request: dict[str, object] = {
        "model": judge_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
        ],
    }
    reasoning_effort = _get_openai_judge_reasoning_effort(judge_model)
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
    else:
        request["temperature"] = 0.0

    response = await client.chat.completions.create(
        **request,
    )
    raw = response.choices[0].message.content or ""
    return parse_judge_response(raw), raw


async def _judge_document_anthropic(
    *,
    case: EvalCase,
    generated_document: str,
    judge_model: str,
    judge_prompt_version: str,
) -> tuple[JudgeResult, str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic judge evals")

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    judge_template = load_judge_prompt(judge_prompt_version)
    prompt = render_judge_prompt(
        judge_template,
        case=case,
        generated_document=generated_document,
    )
    response = await client.messages.create(
        model=judge_model,
        max_tokens=ANTHROPIC_JUDGE_MAX_TOKENS,
        system=prompt,
        messages=[
            {
                "role": "user",
                "content": "Evalua el documento y responde solo con el objeto JSON solicitado.",
            }
        ],
    )
    raw_parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            raw_parts.append(text)
    raw = "".join(raw_parts).strip()

    last_error: ValueError | None = None
    for attempt in range(ANTHROPIC_JUDGE_REPAIR_ATTEMPTS + 1):
        try:
            return parse_judge_response(raw), raw
        except ValueError as exc:
            last_error = exc
            if attempt == ANTHROPIC_JUDGE_REPAIR_ATTEMPTS:
                break
            repair_response = await client.messages.create(
                model=judge_model,
                max_tokens=ANTHROPIC_JUDGE_MAX_TOKENS,
                system=prompt,
                messages=[
                    {
                        "role": "user",
                        "content": _build_anthropic_judge_repair_message(
                            parse_error=str(exc),
                            previous_raw=raw,
                        ),
                    }
                ],
            )
            repair_parts: list[str] = []
            for block in repair_response.content:
                text = getattr(block, "text", None)
                if text:
                    repair_parts.append(text)
            raw = "".join(repair_parts).strip()

    assert last_error is not None
    raise ValueError(
        "anthropic_judge_response_invalid_after_repair_attempts: "
        f"{last_error}; raw={raw[:500]}"
    ) from last_error


async def _run_judges_for_document(
    *,
    case: EvalCase,
    generated_document: str,
    judge_specs: list[JudgeSpec],
    judge_prompt_version: str,
) -> list[dict[str, object]]:
    async def _run_single_judge(judge_spec: JudgeSpec) -> dict[str, object]:
        judge_result, raw_judge_response = await judge_document(
            case=case,
            generated_document=generated_document,
            judge_provider=judge_spec.provider,
            judge_model=judge_spec.model,
            judge_prompt_version=judge_prompt_version,
        )
        return {
            "judge_alias": judge_spec.alias,
            "judge_provider": judge_spec.provider,
            "judge_model": judge_spec.model,
            "judge_result": judge_result.to_dict(),
            "judge_raw_response": raw_judge_response,
        }

    return await asyncio.gather(
        *[_run_single_judge(judge_spec) for judge_spec in judge_specs]
    )


def _print_run_score_summaries(summaries: list[RunScoreSummary]) -> None:
    if not summaries:
        return

    grouped_by_judge: dict[tuple[str, str, str], list[RunScoreSummary]] = {}
    for summary in summaries:
        grouped_by_judge.setdefault(
            (summary.judge_alias, summary.judge_provider, summary.judge_model), []
        ).append(summary)

    print(
        "\nRun score summary (overall = weighted blend with critical-invented "
        "hard cap and safety gate):"
    )
    for judge_key in sorted(grouped_by_judge):
        judge_alias, judge_provider, judge_model = judge_key
        judge_summaries = grouped_by_judge[judge_key]
        print(f"\nJudge {judge_alias}:{judge_model} ({judge_provider})")
        for summary in judge_summaries:
            print(
                f"- {summary.model_alias}:{summary.model} "
                f"({summary.evaluated_output_count} outputs)"
            )
            for dimension in JUDGE_SCORE_DIMENSIONS:
                raw = summary.dimension_averages[dimension]
                effective = summary.effective_dimension_averages[dimension]
                suffix = "" if raw == effective else f"  (effective {effective:.2f})"
                print(f"    {dimension}: {raw:.2f}{suffix}")
            print(f"    safety_gate_failures: {summary.safety_gate_failures}")
            print(f"    critical_invented_count: {summary.critical_invented_count}")
            print(f"    critical_missing_count: {summary.critical_missing_count}")
            print(
                f"    critical_contradiction_count: "
                f"{summary.critical_contradiction_count}"
            )
            print(
                f"    critical_dosing_error_count: "
                f"{summary.critical_dosing_error_count}"
            )
            print("    findings_by_case:")
            for case_findings in summary.findings_by_case:
                print(f"      {case_findings.case_id}:")
                if (
                    not case_findings.invented_info
                    and not case_findings.missing_info
                    and not case_findings.contradiction_info
                    and not case_findings.dosing_error_info
                ):
                    print("        - (none)")
                    continue
                for finding in case_findings.invented_info:
                    print(f"        - invented [{finding.severity}] {finding.item}")
                for finding in case_findings.contradiction_info:
                    print(f"        - contradiction [{finding.severity}] {finding.item}")
                for finding in case_findings.dosing_error_info:
                    print(f"        - dosing_error [{finding.severity}] {finding.item}")
                for finding in case_findings.missing_info:
                    print(
                        f"        - missing [{finding.severity}/{finding.kind}] "
                        f"{finding.item}"
                    )
            print(f"    overall_score: {summary.overall_score:.2f}")
            print(
                "    overall_time_to_first_token_ms: "
                f"{summary.overall_time_to_first_token_ms}"
            )
            print(
                "    overall_time_after_first_token_ms: "
                f"{summary.overall_time_after_first_token_ms}"
            )
            if summary.token_metric_sample_count:
                print(
                    "    total_input_tokens: "
                    f"{summary.total_input_tokens} "
                    f"({summary.token_metric_sample_count}/"
                    f"{summary.evaluated_output_count} outputs)"
                )
                print(f"    total_output_tokens: {summary.total_output_tokens}")
                print(f"    total_thinking_tokens: {summary.total_thinking_tokens}")
                print(
                    "    total_estimated_cost_usd: "
                    f"${summary.total_estimated_cost_usd:.6f}"
                )

        print("\nOverall by model (mean effective score per dimension):")
        for summary in judge_summaries:
            scores = " ".join(
                f"{dimension.removesuffix('_score')}="
                f"{summary.effective_dimension_averages[dimension]:.2f}"
                for dimension in JUDGE_SCORE_DIMENSIONS
            )
            print(
                f"  - {summary.model_alias}:{summary.model} "
                f"{scores} "
                f"overall={summary.overall_score:.2f}"
            )


async def run() -> Path:
    load_dotenv(WORKER_ROOT / ".env.local", override=False)
    load_dotenv(EVALS_ROOT / ".env.local", override=True)
    args = parse_args()
    generation_config = build_generation_config(args)

    template_path = resolve_template_file(args.template_file)
    template_file = str(template_path.relative_to(EVALS_ROOT))
    cases = select_cases(
        load_cases(Path(args.cases), template_file=args.template_file),
        count=args.count,
        last=args.last,
        case_id=args.case_id,
    )
    model_specs = parse_model_specs(args.models)
    judge_specs = parse_judge_specs(
        args.judges,
        default_provider=args.judge_provider,
        default_model=args.judge_model,
    )
    prompt_template = load_prompt_version(args.prompt_version)
    judge_prompt = load_judge_prompt(args.judge_prompt_version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Running {len(cases)} cases across {len(model_specs)} models "
        f"with template={template_file} "
        f"and judges="
        + ",".join(f"{spec.alias}:{spec.model}" for spec in judge_specs)
    )

    run_started_at = datetime.now(UTC)
    results: dict[str, object] = {
        "run_started_at": run_started_at.isoformat(),
        "prompt_version": args.prompt_version,
        "judge_prompt_version": args.judge_prompt_version,
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "judges": [asdict(spec) for spec in judge_specs],
        "cases_file": str(Path(args.cases)),
        "template_file": template_file,
        "requested_case_id": args.case_id,
        "count_limit": args.count,
        "last_limit": args.last,
        "selected_case_count": len(cases),
        "models": [asdict(spec) for spec in model_specs],
        "generation_config": asdict(generation_config),
        "prompt_template_preview": prompt_template[:80],
        "judge_prompt_preview": judge_prompt[:80],
        "case_results": [],
    }

    for case in cases:
        print(f"- Case {case.id}")
        case_result: dict[str, object] = {
            "case_id": case.id,
            "notes": case.notes,
            "outputs": [],
        }
        for spec in model_specs:
            print(f"  - Model {spec.alias}:{spec.model}")
            generated_document, generation_reasoning, generation_metrics = (
                await generate_document(
                    case,
                    spec,
                    args.prompt_version,
                    generation_config,
                )
            )
            if (
                not generated_document.strip()
                and (generation_metrics.thinking_tokens or 0) > 0
            ):
                print(
                    "    ! Empty generated_document with thinking tokens; "
                    "see generation_reasoning in results JSON"
                )
            elif generation_reasoning:
                preview = generation_reasoning[:120].replace("\n", " ")
                print(f"    - Captured reasoning preview: {preview}...")
            for judge_spec in judge_specs:
                print(
                    f"    - Judge {judge_spec.alias}:{judge_spec.model}"
                )
            judge_outputs = await _run_judges_for_document(
                case=case,
                generated_document=generated_document,
                judge_specs=judge_specs,
                judge_prompt_version=args.judge_prompt_version,
            )
            primary_judge_output = judge_outputs[0]
            output_payload: dict[str, object] = {
                    "model_alias": spec.alias,
                    "provider": spec.provider,
                    "model": spec.model,
                    "generated_document": generated_document,
                    "generation_metrics": generation_metrics.to_dict(),
                    "judge_result": primary_judge_output["judge_result"],
                    "judge_raw_response": primary_judge_output["judge_raw_response"],
                    "judge_outputs": judge_outputs,
                }
            if generation_reasoning:
                output_payload["generation_reasoning"] = generation_reasoning
            case_result["outputs"].append(output_payload)
        results["case_results"].append(case_result)

    run_score_summaries = build_run_score_summaries(results["case_results"])
    results["run_score_summary"] = [summary.to_dict() for summary in run_score_summaries]
    _print_run_score_summaries(run_score_summaries)

    output_path = results_dir / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Saved eval results to {output_path}")
    return output_path


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
