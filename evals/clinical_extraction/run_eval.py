from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend_fastapi"
WORKER_ROOT = PROJECT_ROOT / "clinical_extraction_worker"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domains.clinical_extraction.debug_controller import (  # noqa: E402
    run_debug_clinical_extraction,
)
from app.domains.clinical_extraction.schemas import DebugClinicalExtractionRequest  # noqa: E402
from evals.clinical_extraction.lib import (  # noqa: E402
    DEFAULT_EXTRACTION_PROMPT_VERSION,
    EVALS_ROOT,
    EXTRACTION_PROMPT_RUNTIME_SOURCE,
    JUDGE_SCORE_DIMENSIONS,
    EvalCase,
    JudgeResult,
    build_run_score_summaries,
    extraction_prompt_log_path,
    load_cases,
    load_extraction_prompt_log,
    load_judge_prompt,
    normalize_extraction_prompt_version,
    parse_judge_response,
    parse_model_specs,
    render_judge_prompt,
    select_cases,
)


DEFAULT_CASES_PATH = EVALS_ROOT / "cases.json"
DEFAULT_RESULTS_DIR = EVALS_ROOT / "results"
DEFAULT_JUDGE_PROVIDER = "openai"
DEFAULT_JUDGE_MODEL = "gpt-5.4"
DEFAULT_JUDGE_PROMPT_VERSION = "clinical_extraction_judge_v001"
DEFAULT_JUDGE_REASONING_EFFORT = "medium"
DEFAULT_WORKER_BASE_URL = "http://localhost:8093"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_EXTRACTION_MAX_CONCURRENT = 1


def _env_or_default(name: str, fallback: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local evals for ClinicalMentionsV2 extraction models."
    )
    parser.add_argument(
        "--cases",
        default=os.environ.get("EVAL_CASES_FILE", str(DEFAULT_CASES_PATH)),
    )
    parser.add_argument(
        "--models",
        default=os.environ.get(
            "MODELS",
            ",".join(
                [
                    f"gemini:{_env_or_default('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}",
                    f"openai:{_env_or_default('OPENAI_MODEL', DEFAULT_OPENAI_MODEL)}",
                    f"anthropic:{_env_or_default('ANTHROPIC_MODEL', DEFAULT_ANTHROPIC_MODEL)}",
                ]
            ),
        ),
        help="Comma-separated list like gemini:model,openai:model,anthropic:model",
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
        "--judge-reasoning-effort",
        default=_env_or_default(
            "JUDGE_REASONING_EFFORT",
            DEFAULT_JUDGE_REASONING_EFFORT,
        ),
        choices=("minimal", "low", "medium", "high", "xhigh"),
    )
    parser.add_argument(
        "--judge-prompt-version",
        default=_env_or_default(
            "JUDGE_PROMPT_VERSION",
            DEFAULT_JUDGE_PROMPT_VERSION,
        ),
    )
    parser.add_argument(
        "--extraction-prompt-version",
        default=_env_or_default(
            "EXTRACTION_PROMPT_VERSION",
            DEFAULT_EXTRACTION_PROMPT_VERSION,
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
    )
    parser.add_argument(
        "--case-id",
        default=os.environ.get("CASE_ID") or None,
    )
    args = parser.parse_args()
    if args.count is not None and args.last is not None:
        parser.error("--count and --last cannot be used together")
    return args


async def run_extraction_case(
    case: EvalCase,
    *,
    provider: str,
    model: str,
    worker_base_url: str,
    extraction_semaphore: asyncio.Semaphore,
) -> dict[str, object]:
    try:
        async with extraction_semaphore:
            response = await run_debug_clinical_extraction(
                payload=DebugClinicalExtractionRequest(
                    transcript_json=case.transcript_json,
                    provider=provider,
                    model=model,
                ),
                db_session=object(),
                settings=SimpleNamespace(
                    clinical_extraction_worker_base_url=worker_base_url,
                ),
            )
    except HTTPException as exc:
        session_id = str(case.transcript_json.get("session_id") or case.id)
        return {
            "session_id": session_id,
            "status": "failed_extraction",
            "raw_mentions": None,
            "processed_mentions": None,
            "evidence": [],
            "grounding_stats": {},
            "extraction_model": model,
            "provider": provider,
            "model": model,
            "latency_ms": None,
            "error_code": f"http_{exc.status_code}",
            "error_detail": str(exc.detail),
        }

    return {
        "session_id": response.session_id,
        "status": response.status,
        "raw_mentions": response.raw_mentions,
        "processed_mentions": response.processed_mentions,
        "evidence": [item.model_dump() for item in response.evidence],
        "grounding_stats": response.grounding_stats,
        "extraction_model": response.extraction_model,
        "provider": provider,
        "model": model,
        "latency_ms": response.latency_ms,
        "error_code": response.error_code,
    }


def _judge_uses_reasoning_effort(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized == "gpt-5.4" or normalized.startswith("gpt-5.4-")


async def judge_extraction(
    *,
    case: EvalCase,
    processed_mentions: dict[str, object],
    grounding_stats: dict[str, object],
    judge_provider: str,
    judge_model: str,
    judge_prompt_version: str,
    judge_reasoning_effort: str,
) -> tuple[JudgeResult, str]:
    normalized_provider = judge_provider.strip().lower()
    if normalized_provider != "openai":
        raise ValueError(f"Unsupported judge provider: {judge_provider}")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for OpenAI judge evals")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    prompt = render_judge_prompt(
        load_judge_prompt(judge_prompt_version),
        case=case,
        processed_mentions=processed_mentions,
        grounding_stats=grounding_stats,
    )
    request: dict[str, object] = {
        "model": judge_model,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": prompt}],
    }
    if _judge_uses_reasoning_effort(judge_model):
        request["reasoning_effort"] = judge_reasoning_effort
    else:
        request["temperature"] = 0.0
    response = await client.chat.completions.create(**request)
    raw = response.choices[0].message.content or ""
    return parse_judge_response(raw), raw


async def _evaluate_model_for_case(
    case: EvalCase,
    *,
    provider: str,
    model: str,
    worker_base_url: str,
    extraction_semaphore: asyncio.Semaphore,
    judge_provider: str,
    judge_model: str,
    judge_prompt_version: str,
    judge_reasoning_effort: str,
) -> dict[str, object]:
    base_output = {
        "model_alias": provider,
        "provider": provider,
        "model": model,
    }
    try:
        extraction_output = await run_extraction_case(
            case,
            provider=provider,
            model=model,
            worker_base_url=worker_base_url,
            extraction_semaphore=extraction_semaphore,
        )
    except Exception as exc:
        return {
            **base_output,
            "extraction_output": {
                "session_id": str(case.transcript_json.get("session_id") or case.id),
                "status": "failed_extraction",
                "error_code": exc.__class__.__name__,
                "error_detail": str(exc),
            },
            "judge_result": None,
            "judge_raw_response": None,
            "judge_error": "skipped_extraction_failed",
        }

    if extraction_output.get("status") != "extracted":
        return {
            **base_output,
            "extraction_output": extraction_output,
            "judge_result": None,
            "judge_raw_response": None,
            "judge_error": "skipped_extraction_failed",
        }

    try:
        judge_result, judge_raw_response = await judge_extraction(
            case=case,
            processed_mentions=(
                extraction_output.get("processed_mentions") or {"mentions": []}
            ),
            grounding_stats=(extraction_output.get("grounding_stats") or {}),
            judge_provider=judge_provider,
            judge_model=judge_model,
            judge_prompt_version=judge_prompt_version,
            judge_reasoning_effort=judge_reasoning_effort,
        )
    except Exception as exc:
        return {
            **base_output,
            "extraction_output": extraction_output,
            "judge_result": None,
            "judge_raw_response": None,
            "judge_error": exc.__class__.__name__,
            "judge_error_detail": str(exc),
        }

    return {
        **base_output,
        "extraction_output": extraction_output,
        "judge_result": judge_result.to_dict(),
        "judge_raw_response": judge_raw_response,
    }


def _refresh_run_score_summary(results: dict[str, object]) -> None:
    case_results = results.get("case_results")
    if not isinstance(case_results, list):
        results["run_score_summary"] = []
        return
    results["run_score_summary"] = [
        summary.to_dict()
        for summary in build_run_score_summaries(case_results)
    ]


def _persist_results(output_path: Path, results: dict[str, object]) -> None:
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _print_run_score_summaries(run_score_summaries: list[dict[str, object]]) -> None:
    print("\nOverall by model:")
    for summary in run_score_summaries:
        dimensions = " ".join(
            f"{dimension.removesuffix('_score')}="
            f"{summary['dimension_averages'][dimension]:.2f}"
            for dimension in JUDGE_SCORE_DIMENSIONS
        )
        print(
            f"  - {summary['model_alias']}:{summary['model']} "
            f"{dimensions} overall={summary['overall_score']:.2f}"
        )
        print(
            "    critical_counts: "
            f"invented={summary['critical_invented_count']} "
            f"missing={summary['critical_missing_count']} "
            f"atomicity={summary['critical_atomicity_issue_count']} "
            f"coding={summary['critical_coding_issue_count']}"
        )


async def run() -> Path:
    load_dotenv(BACKEND_ROOT / ".env.local", override=False)
    load_dotenv(WORKER_ROOT / ".env.local", override=False)
    load_dotenv(EVALS_ROOT / ".env.local", override=True)
    args = parse_args()

    cases = select_cases(
        load_cases(Path(args.cases)),
        count=args.count,
        last=args.last,
        case_id=args.case_id,
    )
    model_specs = parse_model_specs(args.models)
    extraction_prompt_version = normalize_extraction_prompt_version(
        args.extraction_prompt_version
    )
    extraction_prompt_log = load_extraction_prompt_log(extraction_prompt_version)
    extraction_prompt_log_file = extraction_prompt_log_path(extraction_prompt_version)
    judge_prompt = load_judge_prompt(args.judge_prompt_version)
    worker_base_url = os.environ.get(
        "CLINICAL_EXTRACTION_WORKER_BASE_URL",
        DEFAULT_WORKER_BASE_URL,
    ).strip()
    extraction_max_concurrent = max(
        1,
        int(
            os.environ.get(
                "EXTRACTION_MAX_CONCURRENT",
                str(DEFAULT_EXTRACTION_MAX_CONCURRENT),
            )
        ),
    )
    extraction_semaphore = asyncio.Semaphore(extraction_max_concurrent)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Running {len(cases)} cases across {len(model_specs)} models "
        f"(selection from {Path(args.cases).name}; --count/--last filter cases only) "
        f"with judge={args.judge_provider}:{args.judge_model} "
        f"({args.judge_reasoning_effort}) "
        f"extraction_prompt_version={extraction_prompt_version} "
        f"(runtime={EXTRACTION_PROMPT_RUNTIME_SOURCE}) "
        f"extraction_max_concurrent={extraction_max_concurrent}"
    )

    run_started_at = datetime.now(UTC)
    output_path = results_dir / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    results: dict[str, object] = {
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": None,
        "run_status": "running",
        "run_error": None,
        "output_path": str(output_path),
        "cases_file": str(Path(args.cases)),
        "requested_case_id": args.case_id,
        "count_limit": args.count,
        "last_limit": args.last,
        "selected_case_count": len(cases),
        "completed_case_count": 0,
        "models": [asdict(spec) for spec in model_specs],
        "judge_provider": args.judge_provider,
        "judge_model": args.judge_model,
        "judge_reasoning_effort": args.judge_reasoning_effort,
        "judge_prompt_version": args.judge_prompt_version,
        "judge_prompt_preview": judge_prompt[:80],
        "extraction_prompt_version": extraction_prompt_version,
        "extraction_prompt_log_file": str(
            extraction_prompt_log_file.relative_to(EVALS_ROOT)
        ),
        "extraction_prompt_runtime_source": EXTRACTION_PROMPT_RUNTIME_SOURCE,
        "extraction_prompt_preview": extraction_prompt_log[:80],
        "extraction_max_concurrent": extraction_max_concurrent,
        "case_results": [],
        "run_score_summary": [],
    }
    _persist_results(output_path, results)
    print(f"Writing incremental results to {output_path}")

    try:
        for case in cases:
            print(f"- Case {case.id}")
            case_result: dict[str, object] = {
                "case_id": case.id,
                "notes": case.notes,
                "outputs": [],
            }
            results["case_results"].append(case_result)
            _persist_results(output_path, results)

            for spec in model_specs:
                print(f"  - Run {spec.alias}:{spec.model}")
                output = await _evaluate_model_for_case(
                    case,
                    provider=spec.provider,
                    model=spec.model,
                    worker_base_url=worker_base_url,
                    extraction_semaphore=extraction_semaphore,
                    judge_provider=args.judge_provider,
                    judge_model=args.judge_model,
                    judge_prompt_version=args.judge_prompt_version,
                    judge_reasoning_effort=args.judge_reasoning_effort,
                )
                case_result["outputs"].append(output)
                _refresh_run_score_summary(results)
                _persist_results(output_path, results)

            results["completed_case_count"] = len(results["case_results"])

        results["run_status"] = "completed"
    except (KeyboardInterrupt, asyncio.CancelledError) as exc:
        results["run_status"] = "partial"
        results["run_error"] = "interrupted"
        raise exc
    except Exception as exc:
        results["run_status"] = "partial"
        results["run_error"] = f"{exc.__class__.__name__}: {exc}"
        raise
    finally:
        results["run_finished_at"] = datetime.now(UTC).isoformat()
        _refresh_run_score_summary(results)
        _persist_results(output_path, results)

    _print_run_score_summaries(results["run_score_summary"])
    print(f"Saved eval results to {output_path} (status={results['run_status']})")
    return output_path


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nInterrupted. Partial results were saved to the run output file.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
