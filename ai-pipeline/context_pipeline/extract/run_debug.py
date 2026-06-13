from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    default_model_for_provider,
    normalize_provider_name,
)
from context_pipeline.decompose.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    load_context_cases,
    select_context_case,
)
from context_pipeline.extract.extract import run_extract_fixture  # noqa: E402
from context_pipeline.extract.lib import (  # noqa: E402
    DEFAULT_EXTRACT_TOKEN_BUDGET,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_PROMPT_VERSION,
    MODULE_ROOT,
    enrich_extract_result_for_export,
    format_extract_debug_output,
    load_document_fixture,
    load_prompt,
    prompt_file_path,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug patient-document extract into clinical claims."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--document-file",
        default=None,
        help="Fixture JSON under context_pipeline/cases (defaults to first in case).",
    )
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT_VERSION),
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=int(
            os.environ.get(
                "CONTEXT_EXTRACT_TOKEN_BUDGET",
                str(DEFAULT_EXTRACT_TOKEN_BUDGET),
            )
        ),
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", str(DEFAULT_RESULTS_DIR)),
    )
    parser.add_argument(
        "--output-detail",
        default=os.environ.get("OUTPUT_DETAIL", DEFAULT_OUTPUT_DETAIL),
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(AI_PIPELINE_ROOT / ".env.local", override=False)
    load_dotenv(MODULE_ROOT / ".env.local", override=True)
    args = parse_args()
    output_detail = normalize_output_detail(args.output_detail)
    prompt_version = normalize_prompt_version(args.prompt_version)
    provider = normalize_provider_name(args.provider)
    model = (args.model or default_model_for_provider(provider)).strip()
    model_spec = ModelSpec(alias=provider, provider=provider, model=model)
    prompt_path = prompt_file_path(prompt_version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    cases_index = Path(args.cases)
    cases_dir = cases_index.parent
    case_meta = select_context_case(
        load_context_cases(cases_index),
        case_id=args.case_id,
    )
    document_file = args.document_file or (
        case_meta.document_files[0] if case_meta.document_files else None
    )
    if not document_file:
        print("error: case has no document_files and --document-file not set")
        return 1

    fixture = load_document_fixture(cases_dir / document_file)
    system_prompt = load_prompt(prompt_version)
    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{fixture.document_id}_{provider}.json"
    )

    print(
        f"case={case_meta.id} document={fixture.document_id} "
        f"provider={provider} model={model} prompt_version={prompt_version}"
    )
    try:
        result, raw_responses = run_extract_fixture(
            fixture=fixture,
            cases_dir=cases_dir,
            model_spec=model_spec,
            system_prompt=system_prompt,
            token_budget=args.token_budget,
        )
    except Exception as exc:
        print(f"\nerror: {exc}")
        return 1

    output_payload: dict[str, object] = {
        "provider": provider,
        "model": model,
        "extract_result": enrich_extract_result_for_export(result),
    }
    if output_detail == "full":
        output_payload["raw_responses"] = raw_responses

    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": case_meta.id,
        "session_id": case_meta.session_id,
        "document_file": document_file,
        "cases_file": str(cases_index),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        **output_payload,
    }
    output_path.write_text(
        json.dumps(result_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n" + format_extract_debug_output(result))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
