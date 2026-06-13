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
    call_llm_detailed,
    default_model_for_provider,
    normalize_provider_name,
)
from generation.generate import run_section_generation  # noqa: E402
from generation.lib import (  # noqa: E402
    DEFAULT_CLASSIFICATION_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_TEMPLATES_DIR,
    MODULE_ROOT,
    enrich_section_generation_result_for_export,
    format_generation_output_for_detail,
    load_classification_assignments,
    load_prompt,
    plan_section_generation,
    prompt_file_path,
    render_section_user_payload,
    template_id_from_classification_result,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug generation for a single template section."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CLASSIFICATION_CASES_INDEX))
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--section-id", required=True)
    parser.add_argument("--classification-result", required=True)
    parser.add_argument("--template-id", default=None)
    parser.add_argument(
        "--templates-dir",
        default=str(DEFAULT_TEMPLATES_DIR),
    )
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument("--model", default=None)
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
    parser.add_argument("--dump-raw", action="store_true")
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
        templates_dir = templates_dir.resolve()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    classification_result_path = Path(args.classification_result)
    assignments = load_classification_assignments(classification_result_path)
    clusters = load_session_clusters(Path(args.cases), args.session_id)
    clusters_by_id = {cluster.id: cluster for cluster in clusters}
    template_id = (
        args.template_id
        or template_id_from_classification_result(classification_result_path)
        or clusters[0].template_id
    ).strip()
    template = load_template(template_id, templates_dir=templates_dir)
    system_prompt = load_prompt(prompt_version)
    section_plan = plan_section_generation(assignments, clusters_by_id, template)
    job = next(
        (item for item in section_plan.jobs if item.section_id == args.section_id),
        None,
    )
    if job is None:
        print(f"error: section has no clusters to generate: {args.section_id}")
        return 1

    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{args.section_id}_{provider}.json"
    )

    print(
        f"session={args.session_id} section={args.section_id} "
        f"clusters={len(job.clusters)} template={template_id} "
        f"provider={provider} model={model} prompt_version={prompt_version}"
    )
    try:
        result, llm_response, response_time_ms = run_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        if args.dump_raw:
            try:
                raw_response = call_llm_detailed(
                    provider=provider,
                    model=model,
                    system=system_prompt,
                    user=render_section_user_payload(
                        section=job.section,
                        clusters=job.clusters,
                        enrichment_claims=job.enrichment_claims,
                        template=template,
                    ),
                ).content
                print("\nraw response:")
                print(raw_response)
            except Exception:
                pass
        print(f"\nerror: {exc}")
        return 1

    output_payload = format_generation_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "generation_result": enrich_section_generation_result_for_export(
                result,
                heading=job.section.heading,
                cluster_ids=job.cluster_ids,
            ),
            "raw_response": llm_response.content,
            "thinking": llm_response.thinking,
            "thinking_source": llm_response.thinking_source,
            "llm_usage": llm_response.usage,
            "llm_request_params": llm_response.request_params,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "response_time_ms": response_time_ms,
        "output_path": str(output_path),
        "session_id": args.session_id,
        "section_id": args.section_id,
        "cluster_ids": job.cluster_ids,
        "classification_result_file": str(classification_result_path),
        "template_id": template_id,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + result.content)
    print(f"\nWrote {output_path} (response_time_ms={response_time_ms})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
