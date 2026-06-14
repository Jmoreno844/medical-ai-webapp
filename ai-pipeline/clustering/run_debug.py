from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    call_llm,
    default_model_for_provider,
    normalize_provider_name,
)
from common.transcripts import (  # noqa: E402
    build_turn_catalog,
    load_cases,
    select_cases,
)
from clustering.cluster import run_clustering_with_repair  # noqa: E402
from clustering.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_PROMPT_VERSION,
    MODULE_ROOT,
    audit_turn_coverage,
    clustering_prompt_reference,
    enrich_clustering_result_for_export,
    format_clustering_output_for_detail,
    format_debug_output,
    format_turn_coverage_audit,
    load_prompt,
    render_clustering_user_payload,
)
from clustering.repair import (  # noqa: E402
    DEFAULT_REPAIR_PROMPT_VERSION,
    clustering_repair_prompt_reference,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug conversation clustering for a single case."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument(
        "--model",
        default=None,
        help="Defaults to provider-specific MODEL env vars.",
    )
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT_VERSION),
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", str(DEFAULT_RESULTS_DIR)),
    )
    parser.add_argument(
        "--output-detail",
        default=os.environ.get("OUTPUT_DETAIL", DEFAULT_OUTPUT_DETAIL),
    )
    parser.add_argument(
        "--dump-raw",
        action="store_true",
        help="Print raw LLM response on parse failure.",
    )
    return parser.parse_args()


def _persist_results(output_path: Path, payload: dict[str, object]) -> None:
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    load_dotenv(AI_PIPELINE_ROOT / ".env.local", override=False)
    load_dotenv(MODULE_ROOT / ".env.local", override=True)
    args = parse_args()
    output_detail = normalize_output_detail(args.output_detail)
    prompt_version = normalize_prompt_version(args.prompt_version)
    provider = normalize_provider_name(args.provider)
    model = (args.model or default_model_for_provider(provider)).strip()
    model_spec = ModelSpec(alias=provider, provider=provider, model=model)
    prompt_path = clustering_prompt_reference(prompt_version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    cases = select_cases(
        load_cases(Path(args.cases)),
        case_id=args.case_id,
    )
    case = cases[0]
    system_prompt = load_prompt(prompt_version)
    catalog = build_turn_catalog(case.transcript_json)
    run_started_at = datetime.now(UTC)
    output_path = (
        results_dir
        / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{case.id}_{provider}.json"
    )

    print(
        f"case={case.id} provider={provider} model={model} "
        f"prompt_version={prompt_version} turns={len(catalog)}"
    )
    repair_prompt_path = clustering_repair_prompt_reference(
        DEFAULT_REPAIR_PROMPT_VERSION
    )
    try:
        session_run = run_clustering_with_repair(
            case=case,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        if args.dump_raw:
            try:
                raw_response = call_llm(
                    provider=provider,
                    model=model,
                    system=system_prompt,
                    user=render_clustering_user_payload(
                        case=case,
                        prompt_version=prompt_version,
                    ),
                )
                print("\n--- raw response ---")
                print(raw_response)
            except Exception as nested_exc:
                print(f"\nraw fetch failed: {nested_exc}")
        print(f"\nerror: {exc}")
        return 1

    result = session_run.result
    raw_response = session_run.llm_response.content
    repair_passes = [repair_pass.to_dict() for repair_pass in session_run.repair_passes]
    coverage = audit_turn_coverage(result, catalog)
    output_payload = format_clustering_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "clustering_result": enrich_clustering_result_for_export(
                result, catalog
            ),
            "turn_coverage": coverage.to_dict(),
            "repair_passes": repair_passes,
            "raw_response": raw_response,
            "thinking": session_run.llm_response.thinking,
            "thinking_source": session_run.llm_response.thinking_source,
            "llm_usage": session_run.llm_response.usage,
            "llm_request_params": session_run.llm_response.request_params,
            "llm_timing": (
                session_run.llm_response.timing.to_dict()
                if session_run.llm_response.timing is not None
                else None
            ),
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "response_time_ms": session_run.response_time_ms
        + session_run.repair_response_time_ms,
        "llm_usage": session_run.llm_response.usage,
        "initial_response_time_ms": session_run.response_time_ms,
        "repair_response_time_ms": session_run.repair_response_time_ms,
        "repair_pass_count": len(repair_passes),
        "repair_prompt_version": DEFAULT_REPAIR_PROMPT_VERSION,
        "repair_prompt_file": repair_prompt_path,
        "output_path": str(output_path),
        "case_id": case.id,
        "case_notes": case.notes,
        "cases_file": str(Path(args.cases)),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": prompt_path,
        "output_detail": output_detail,
        "turn_count": len(catalog),
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + format_debug_output(result, catalog))
    print("\n" + format_turn_coverage_audit(coverage, catalog))
    if repair_passes:
        print(f"\nrepair passes: {len(repair_passes)}")
    print(f"\nWrote {output_path}")
    if args.dump_raw:
        print("\n--- raw response ---")
        print(raw_response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
