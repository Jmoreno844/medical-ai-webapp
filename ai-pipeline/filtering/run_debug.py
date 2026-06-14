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
    render_user_payload,
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
    format_debug_output,
    format_drop_audit,
    format_filtering_output_for_detail,
    load_prompt,
    prompt_file_path,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug conversation filtering for a single case."
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
    prompt_path = prompt_file_path(prompt_version)
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
    try:
        result, llm_response = run_filtering(
            case=case,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        if args.dump_raw:
            try:
                raw_response = call_llm(
                    provider=provider,
                    model=model,
                    system=system_prompt,
                    user=render_user_payload(case),
                )
                print("\n--- raw response ---")
                print(raw_response)
            except Exception as nested_exc:
                print(f"\nraw fetch failed: {nested_exc}")
        print(f"\nerror: {exc}")
        return 1

    drop_audit = audit_drop_turn_ids(result, catalog)
    output_payload = format_filtering_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "filtering_result": enrich_filtering_result_for_export(
                result, catalog
            ),
            "drop_audit": drop_audit.to_dict(),
            "raw_response": llm_response.content,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": case.id,
        "case_notes": case.notes,
        "cases_file": str(Path(args.cases)),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        "turn_count": len(catalog),
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + format_debug_output(result, catalog))
    print("\n" + format_drop_audit(drop_audit))
    print(f"\nWrote {output_path}")
    if args.dump_raw:
        print("\n--- raw response ---")
        print(llm_response.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
