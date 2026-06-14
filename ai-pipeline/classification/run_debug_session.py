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

from classification.batching import (  # noqa: E402
    DEFAULT_INPUT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ENCODING,
)
from classification.classify import run_classification_session  # noqa: E402
from classification.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_TEMPLATES_DIR,
    MODULE_ROOT,
    enrich_classification_batch_result_for_export,
    enrich_classification_session_result_for_export,
    format_batch_assignment_audit,
    format_classification_batch_output_for_detail,
    format_classification_output_for_detail,
    format_session_debug_output,
    load_prompt,
    load_session_clusters,
    prompt_file_path,
)
from classification.templates import load_template  # noqa: E402
from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    default_model_for_provider,
    normalize_provider_name,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug token-batched classification for a full session."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--template-id",
        default=None,
        help="Override template from the first cluster case.",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(DEFAULT_TEMPLATES_DIR),
    )
    parser.add_argument(
        "--input-token-budget",
        type=int,
        default=int(
            os.environ.get(
                "CLASSIFICATION_INPUT_TOKEN_BUDGET",
                str(DEFAULT_INPUT_TOKEN_BUDGET),
            )
        ),
    )
    parser.add_argument(
        "--token-encoding",
        default=os.environ.get(
            "CLASSIFICATION_TOKEN_ENCODING",
            DEFAULT_TOKEN_ENCODING,
        ),
    )
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument(
        "--model",
        default=None,
        help="Defaults to provider-specific MODEL env vars.",
    )
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", "v002"),
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


def _format_batch_plan(batch_plan: object) -> str:
    plan_dict = batch_plan.to_dict()  # type: ignore[attr-defined]
    lines = [
        "batch plan:",
        f"  input_token_budget: {plan_dict['input_token_budget']}",
        f"  template_token_count: {plan_dict['template_token_count']}",
        f"  effective_cluster_budget: {plan_dict['effective_cluster_budget']}",
        f"  batch_count: {plan_dict['batch_count']}",
    ]
    if plan_dict.get("oversize_cluster_ids"):
        lines.append(f"  oversize_cluster_ids: {plan_dict['oversize_cluster_ids']}")
    for batch in plan_dict.get("batches", []):
        if not isinstance(batch, dict):
            continue
        lines.append(
            "  - batch "
            f"{batch.get('batch_index')}: "
            f"clusters={batch.get('cluster_ids')} "
            f"tokens={batch.get('estimated_input_tokens')}"
        )
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
        templates_dir = (MODULE_ROOT / templates_dir).resolve()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    clusters = load_session_clusters(Path(args.cases), args.session_id)
    template_id = (args.template_id or clusters[0].template_id).strip()
    template = load_template(template_id, templates_dir=templates_dir)
    system_prompt = load_prompt(prompt_version)
    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_session_{args.session_id}_{provider}.json"
    )

    print(
        f"session={args.session_id} clusters={len(clusters)} template={template_id} "
        f"provider={provider} model={model} prompt_version={prompt_version} "
        f"input_token_budget={args.input_token_budget}"
    )
    try:
        session_run = run_classification_session(
            session_id=args.session_id,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            input_token_budget=args.input_token_budget,
            token_encoding=args.token_encoding,
        )
    except Exception as exc:
        print(f"\nerror: {exc}")
        return 1

    batch_outputs: list[dict[str, object]] = []
    for batch_run in session_run.batch_runs:
        batch_entry: dict[str, object] = {
            "batch_index": batch_run.batch_index,
            "cluster_ids": [cluster.id for cluster in batch_run.clusters],
            "response_time_ms": batch_run.response_time_ms,
            "classification_result": enrich_classification_batch_result_for_export(
                batch_run.result,
                template,
            ),
            "batch_assignment_audit": batch_run.assignment_audit.to_dict(),  # type: ignore[attr-defined]
            "raw_response": batch_run.raw_response,
            "thinking": batch_run.thinking,
            "thinking_source": batch_run.thinking_source,
            "llm_usage": batch_run.llm_usage,
            "llm_request_params": batch_run.llm_request_params,
        }
        batch_outputs.append(
            format_classification_batch_output_for_detail(batch_entry, output_detail)
        )

    session_export = enrich_classification_session_result_for_export(
        session_run.session_result,
        template,
    )
    output_payload = format_classification_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "classification_session_result": session_export,
            "batch_plan": session_run.batch_plan.to_dict(),
            "batch_assignment_audit": session_run.session_audit.to_dict(),  # type: ignore[attr-defined]
            "batch_outputs": batch_outputs,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug_session",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "total_response_time_ms": session_run.total_response_time_ms,
        "sum_batch_response_time_ms": session_run.sum_batch_response_time_ms,
        "batch_execution_mode": session_run.batch_execution_mode,
        "batch_concurrency": session_run.batch_concurrency,
        "llm_usage_summary": session_run.llm_usage_summary,
        "output_path": str(output_path),
        "session_id": args.session_id,
        "cluster_count": len(clusters),
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
        "input_token_budget": args.input_token_budget,
        "token_encoding": args.token_encoding,
        **output_payload,
    }
    _persist_results(output_path, result_record)

    print("\n" + _format_batch_plan(session_run.batch_plan))
    print("\n" + format_session_debug_output(session_run.session_result, template))
    print("\n" + format_batch_assignment_audit(session_run.session_audit))  # type: ignore[arg-type]
    if session_run.batch_plan.oversize_cluster_ids:
        print(
            "\nWARNING: oversize clusters exceed effective budget: "
            f"{list(session_run.batch_plan.oversize_cluster_ids)}"
        )
    print(
        f"\nWrote {output_path} "
        f"(total_response_time_ms={session_run.total_response_time_ms}, "
        f"llm_usage_summary={session_run.llm_usage_summary})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
