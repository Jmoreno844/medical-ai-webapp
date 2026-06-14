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

from classification.classify import run_classification  # noqa: E402
from classification.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_TEMPLATES_DIR,
    MODULE_ROOT,
    audit_section_ids,
    build_cluster_turns,
    enrich_classification_result_for_export,
    format_classification_output_for_detail,
    format_debug_output,
    format_section_audit,
    load_cluster_cases,
    load_prompt,
    prompt_file_path,
    render_classification_user_payload,
    select_cluster_cases,
)
from classification.templates import load_template  # noqa: E402
from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    call_llm,
    default_model_for_provider,
    normalize_provider_name,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug cluster classification for a single case."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--template-id",
        default=None,
        help="Override template from case manifest.",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(DEFAULT_TEMPLATES_DIR),
    )
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
    templates_dir = Path(args.templates_dir)
    if not templates_dir.is_absolute():
        templates_dir = (MODULE_ROOT / templates_dir).resolve()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    cases = select_cluster_cases(
        load_cluster_cases(Path(args.cases)),
        case_id=args.case_id,
    )
    cluster_case = cases[0]
    template_id = (args.template_id or cluster_case.template_id).strip()
    template = load_template(template_id, templates_dir=templates_dir)
    system_prompt = load_prompt(prompt_version)
    turns = build_cluster_turns(cluster_case.cluster_json)
    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{cluster_case.id}_{provider}.json"
    )

    print(
        f"case={cluster_case.id} template={template_id} provider={provider} "
        f"model={model} prompt_version={prompt_version} turns={len(turns)}"
    )
    try:
        result, raw_response = run_classification(
            cluster_case=cluster_case,
            template=template,
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
                    user=render_classification_user_payload(
                        cluster_case=cluster_case,
                        template=template,
                        prompt_version=prompt_version,
                    ),
                )
                print("\n--- raw response ---")
                print(raw_response)
            except Exception as nested_exc:
                print(f"\nraw fetch failed: {nested_exc}")
        print(f"\nerror: {exc}")
        return 1

    section_audit = audit_section_ids(result, template)
    output_payload = format_classification_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "classification_result": enrich_classification_result_for_export(
                result, template
            ),
            "section_audit": section_audit.to_dict(),
            "raw_response": raw_response,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": cluster_case.id,
        "case_notes": cluster_case.notes,
        "cases_file": str(Path(args.cases)),
        "template_id": template_id,
        "template_file": str(
            (templates_dir / f"{template_id}.json").relative_to(MODULE_ROOT)
        ),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        "turn_count": len(turns),
        "topic_label": cluster_case.cluster_json.get("topic_label"),
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + format_debug_output(result, template, cluster_case))
    print("\n" + format_section_audit(section_audit))
    print(f"\nWrote {output_path}")
    if args.dump_raw:
        print("\n--- raw response ---")
        print(raw_response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
