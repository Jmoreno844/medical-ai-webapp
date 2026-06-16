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

from classification.lib import load_session_clusters  # noqa: E402
from classification.templates import load_template  # noqa: E402
from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    default_model_for_provider,
    normalize_provider_name,
)
from generation.generate import (  # noqa: E402
    resolve_section_concurrency,
    run_generation_session,
)
from generation.lib import (  # noqa: E402
    DEFAULT_CLASSIFICATION_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_SECTION_CONCURRENCY,
    DEFAULT_TEMPLATES_DIR,
    MODULE_ROOT,
    enrich_generation_session_result_for_export,
    enrich_section_generation_result_for_export,
    format_generation_output_for_detail,
    format_section_output_for_detail,
    format_session_debug_output,
    load_section_context_from_record,
    load_section_evidence_from_record,
    load_classification_assignments,
    load_prompt,
    prompt_file_path,
    template_id_from_classification_result,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug parallel per-section generation for a full session."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CLASSIFICATION_CASES_INDEX))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--classification-result", required=True)
    parser.add_argument(
        "--template-id",
        default=None,
        help="Override template from classification result or cluster cases.",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(DEFAULT_TEMPLATES_DIR),
    )
    parser.add_argument(
        "--section-concurrency",
        type=int,
        default=int(
            os.environ.get(
                "GENERATION_SECTION_CONCURRENCY",
                str(DEFAULT_SECTION_CONCURRENCY),
            )
        ),
    )
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument(
        "--model",
        default=None,
        help="Defaults to provider-specific MODEL env vars.",
    )
    parser.add_argument(
        "--claim-classification-result",
        default=None,
        help="Optional claim classification session JSON for enrichment_claims merge.",
    )
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", "v001"),
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


def _persist_results(output_path: Path, payload: dict[str, object]) -> None:
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _format_section_plan(section_plan: object) -> str:
    plan_dict = section_plan.to_dict()  # type: ignore[attr-defined]
    lines = [
        "section plan:",
        f"  job_count: {plan_dict['job_count']}",
        f"  section_ids: {plan_dict['section_ids']}",
        f"  skipped_section_ids: {plan_dict['skipped_section_ids']}",
    ]
    return "\n".join(lines)


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
        templates_dir = templates_dir.resolve()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    classification_result_path = Path(args.classification_result)
    assignments = load_classification_assignments(classification_result_path)
    clusters = load_session_clusters(Path(args.cases), args.session_id)
    section_context = None
    section_evidence = None
    if args.claim_classification_result:
        claim_path = Path(args.claim_classification_result)
        section_context = load_section_context_from_record(claim_path)
        section_evidence = load_section_evidence_from_record(claim_path)
    template_id = (
        args.template_id
        or template_id_from_classification_result(classification_result_path)
        or clusters[0].template_id
    ).strip()
    template = load_template(template_id, templates_dir=templates_dir)
    system_prompt = load_prompt(prompt_version)
    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_session_{args.session_id}_{provider}.json"
    )

    print(
        f"session={args.session_id} clusters={len(clusters)} "
        f"assignments={len(assignments)} template={template_id} "
        f"provider={provider} model={model} prompt_version={prompt_version} "
        f"section_concurrency={resolve_section_concurrency(args.section_concurrency)}"
    )
    try:
        session_run = run_generation_session(
            session_id=args.session_id,
            assignments=assignments,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            section_concurrency=args.section_concurrency,
            section_context=section_context,
            section_evidence=section_evidence,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        print(f"\nerror: {exc}")
        return 1

    cluster_ids_by_section = {
        section_run.section_id: section_run.cluster_ids
        for section_run in session_run.section_runs
    }
    claim_ids_by_section = {
        section_run.section_id: section_run.claim_ids
        for section_run in session_run.section_runs
    }
    section_outputs: list[dict[str, object]] = []
    for section_run in session_run.section_runs:
        section = next(
            section
            for section in template.sections
            if section.section_id == section_run.section_id
        )
        section_entry: dict[str, object] = {
            "section_id": section_run.section_id,
            "cluster_ids": section_run.cluster_ids,
            "claim_ids": section_run.claim_ids,
            "response_time_ms": section_run.response_time_ms,
            "generation_result": enrich_section_generation_result_for_export(
                section_run.result,
                heading=section.heading,
                cluster_ids=section_run.cluster_ids,
                claim_ids=section_run.claim_ids,
            ),
            "raw_response": section_run.raw_response,
            "thinking": section_run.thinking,
            "thinking_source": section_run.thinking_source,
            "llm_usage": section_run.llm_usage,
            "llm_request_params": section_run.llm_request_params,
        }
        section_outputs.append(
            format_section_output_for_detail(section_entry, output_detail)
        )

    session_export = enrich_generation_session_result_for_export(
        session_run.session_result,
        template,
        cluster_ids_by_section=cluster_ids_by_section,
        claim_ids_by_section=claim_ids_by_section,
    )
    output_payload = format_generation_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "generation_session_result": session_export,
            "section_plan": session_run.section_plan.to_dict(),
            "section_outputs": section_outputs,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug_session",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "total_response_time_ms": session_run.total_response_time_ms,
        "sum_section_response_time_ms": session_run.sum_section_response_time_ms,
        "section_execution_mode": session_run.section_execution_mode,
        "section_concurrency": session_run.section_concurrency,
        "llm_usage_summary": session_run.llm_usage_summary,
        "output_path": str(output_path),
        "session_id": args.session_id,
        "cluster_count": len(clusters),
        "cases_file": str(Path(args.cases)),
        "classification_result_file": str(classification_result_path),
        "claim_classification_result_file": (
            str(args.claim_classification_result)
            if args.claim_classification_result
            else None
        ),
        "template_id": template_id,
        "template_file": str(templates_dir / f"{template_id}.json"),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + _format_section_plan(session_run.section_plan))
    print("\n" + format_session_debug_output(session_run.session_result, template))
    print(
        f"\nWrote {output_path} "
        f"(total_response_time_ms={session_run.total_response_time_ms}, "
        f"llm_usage_summary={session_run.llm_usage_summary})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
