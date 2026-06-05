from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
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
    EVALS_ROOT,
    EvalCase,
    GenerationMetrics,
    JudgeResult,
    ModelSpec,
    load_cases,
    load_judge_prompt,
    load_prompt_version,
    parse_judge_response,
    parse_model_specs,
    render_generation_prompt,
    render_judge_prompt,
    select_cases,
)


DEFAULT_CASES_PATH = EVALS_ROOT / "cases.json"
DEFAULT_RESULTS_DIR = EVALS_ROOT / "results"
DEFAULT_PROMPT_VERSION = "document_generation_v001"
DEFAULT_JUDGE_PROMPT_VERSION = "clinical_document_judge_v001"
DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_JUDGE_MODEL = "gpt-4.1-mini"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _env_or_default(name: str, fallback: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or fallback


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
        help="Comma-separated list like gemini:model,anthropic:model",
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
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", str(DEFAULT_RESULTS_DIR)),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.environ["COUNT"]) if os.environ.get("COUNT") else None,
    )
    parser.add_argument(
        "--case-id",
        default=os.environ.get("CASE_ID") or None,
    )
    return parser.parse_args()


def build_settings(provider: str, model: str) -> Settings:
    env_file = WORKER_ROOT / ".env.local"
    return Settings(
        _env_file=str(env_file),
        DOCUMENT_GENERATION_PROVIDER=provider,
        DOCUMENT_GENERATION_MODEL=model,
    )


async def _stream_with_anthropic_api(
    *,
    prompt: str,
    model: str,
    settings: Settings,
):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for Anthropic API evals")

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model=model,
        max_tokens=settings.max_output_tokens,
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:
            if text:
                yield text


async def generate_document(
    case: EvalCase,
    spec: ModelSpec,
    prompt_version: str,
) -> tuple[str, GenerationMetrics]:
    prompt_template = load_prompt_version(prompt_version)
    prompt = render_generation_prompt(prompt_template, case)
    settings = build_settings(spec.provider, spec.model)
    chunks: list[str] = []
    started_at = time.monotonic()
    first_token_at: float | None = None

    if spec.provider == "anthropic_api":
        chunk_iter = _stream_with_anthropic_api(
            prompt=prompt,
            model=spec.model,
            settings=settings,
        )
    else:
        chunk_iter = stream_document_generation(prompt=prompt, settings=settings)

    async for chunk in chunk_iter:
        if first_token_at is None:
            first_token_at = time.monotonic()
        chunks.append(chunk)
    finished_at = time.monotonic()
    if first_token_at is None:
        first_token_at = finished_at

    metrics = GenerationMetrics(
        time_to_first_token_ms=int((first_token_at - started_at) * 1000),
        time_after_first_token_ms=int((finished_at - first_token_at) * 1000),
        total_generation_ms=int((finished_at - started_at) * 1000),
    )
    return "".join(chunks).strip(), metrics


async def judge_document(
    *,
    case: EvalCase,
    generated_document: str,
    judge_provider: str,
    judge_model: str,
    judge_prompt_version: str,
) -> tuple[JudgeResult, str]:
    if judge_provider.strip().lower() != "openai":
        raise ValueError(f"Unsupported judge provider: {judge_provider}")

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
    response = await client.chat.completions.create(
        model=judge_model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    return parse_judge_response(raw), raw


async def run() -> Path:
    load_dotenv(WORKER_ROOT / ".env.local", override=False)
    load_dotenv(EVALS_ROOT / ".env.local", override=True)
    args = parse_args()

    cases = select_cases(
        load_cases(Path(args.cases)),
        count=args.count,
        case_id=args.case_id,
    )
    model_specs = parse_model_specs(args.models)
    prompt_template = load_prompt_version(args.prompt_version)
    judge_prompt = load_judge_prompt(args.judge_prompt_version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Running {len(cases)} cases across {len(model_specs)} models "
        f"with judge={args.judge_provider}:{args.judge_model}"
    )

    run_started_at = datetime.now(UTC)
    results: dict[str, object] = {
        "run_started_at": run_started_at.isoformat(),
        "prompt_version": args.prompt_version,
        "judge_prompt_version": args.judge_prompt_version,
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "cases_file": str(Path(args.cases)),
        "requested_case_id": args.case_id,
        "count_limit": args.count,
        "selected_case_count": len(cases),
        "models": [asdict(spec) for spec in model_specs],
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
            generated_document, generation_metrics = await generate_document(
                case,
                spec,
                args.prompt_version,
            )
            judge_result, raw_judge_response = await judge_document(
                case=case,
                generated_document=generated_document,
                judge_provider=args.judge_provider,
                judge_model=args.judge_model,
                judge_prompt_version=args.judge_prompt_version,
            )
            case_result["outputs"].append(
                {
                    "model_alias": spec.alias,
                    "provider": spec.provider,
                    "model": spec.model,
                    "generated_document": generated_document,
                    "generation_metrics": generation_metrics.to_dict(),
                    "judge_result": judge_result.to_dict(),
                    "judge_raw_response": raw_judge_response,
                }
            )
        results["case_results"].append(case_result)

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
