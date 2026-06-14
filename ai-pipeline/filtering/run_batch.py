from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import parse_model_specs  # noqa: E402
from common.transcripts import (  # noqa: E402
    build_turn_catalog,
    load_cases,
    select_cases,
)
from filtering.filter import run_filtering  # noqa: E402
from filtering.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_PROMPT_VERSION,
    MODULE_ROOT,
    audit_drop_turn_ids,
    enrich_filtering_result_for_export,
    filtering_prompt_reference,
    format_filtering_output_for_detail,
    load_prompt,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_GROQ_MODEL = "qwen/qwen3-32b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run conversation filtering across cases and models."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument(
        "--models",
        default=os.environ.get(
            "MODELS",
            f"openai:{DEFAULT_OPENAI_MODEL},groq:{DEFAULT_GROQ_MODEL}",
        ),
    )
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT_VERSION),
    )
    parser.add_argument(
        "--output-detail",
        default=os.environ.get("OUTPUT_DETAIL", DEFAULT_OUTPUT_DETAIL),
    )
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--last", type=int, default=None)
    parser.add_argument("--case-id", default=None)
    return parser.parse_args()


def _persist_results(output_path: Path, results: dict[str, object]) -> None:
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    load_dotenv(AI_PIPELINE_ROOT / ".env.local", override=False)
    load_dotenv(MODULE_ROOT / ".env.local", override=True)
    args = parse_args()
    output_detail = normalize_output_detail(args.output_detail)
    prompt_version = normalize_prompt_version(args.prompt_version)
    model_specs = parse_model_specs(args.models)
    system_prompt = load_prompt(prompt_version)
    prompt_path = filtering_prompt_reference(prompt_version)

    cases = select_cases(
        load_cases(Path(args.cases)),
        count=args.count,
        last=args.last,
        case_id=args.case_id,
    )
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

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
        "prompt_version": prompt_version,
        "prompt_file": prompt_path,
        "prompt_preview": system_prompt[:80],
        "output_detail": output_detail,
        "case_results": [],
    }
    _persist_results(output_path, results)

    print(
        f"Running {len(cases)} cases across {len(model_specs)} models "
        f"prompt_version={prompt_version} output_detail={output_detail}"
    )
    print(f"Writing incremental results to {output_path}")

    case_results: list[dict[str, object]] = []
    try:
        for case in cases:
            case_entry: dict[str, object] = {
                "case_id": case.id,
                "notes": case.notes,
                "outputs": [],
            }
            for model_spec in model_specs:
                output_entry: dict[str, object] = {
                    "model_alias": model_spec.alias,
                    "provider": model_spec.provider,
                    "model": model_spec.model,
                }
                try:
                    filtering_result, llm_response = run_filtering(
                        case=case,
                        model_spec=model_spec,
                        system_prompt=system_prompt,
                        prompt_version=prompt_version,
                    )
                    catalog = build_turn_catalog(case.transcript_json)
                    drop_audit = audit_drop_turn_ids(filtering_result, catalog)
                    output_entry["filtering_result"] = (
                        enrich_filtering_result_for_export(
                            filtering_result, catalog
                        )
                    )
                    output_entry["drop_audit"] = drop_audit.to_dict()
                    output_entry["raw_response"] = llm_response.content
                    if not drop_audit.is_valid:
                        model_label = (
                            f"{model_spec.provider}:{model_spec.model}"
                        )
                        print(
                            "WARNING: invalid drop_turn_ids "
                            f"case={case.id} model={model_label} "
                            f"extra={drop_audit.extra_turn_ids} "
                            f"duplicates={drop_audit.duplicate_turn_ids}"
                        )
                except Exception as exc:
                    output_entry["error"] = str(exc)
                case_entry["outputs"].append(
                    format_filtering_output_for_detail(output_entry, output_detail)
                )
                _persist_results(output_path, results)
            case_results.append(case_entry)
            results["case_results"] = case_results
            results["completed_case_count"] = len(case_results)
            _persist_results(output_path, results)
    except Exception as exc:
        results["run_status"] = "partial"
        results["run_error"] = str(exc)
        results["run_finished_at"] = datetime.now(UTC).isoformat()
        _persist_results(output_path, results)
        print(f"run failed: {exc}")
        return 1

    results["run_status"] = "completed"
    results["run_finished_at"] = datetime.now(UTC).isoformat()
    results["case_results"] = case_results
    _persist_results(output_path, results)
    print(f"completed: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
