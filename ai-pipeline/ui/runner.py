from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from classification.batching import (
    DEFAULT_INPUT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ENCODING,
)
from classification.classify import run_classification_session
from classification.lib import (
    DEFAULT_CASES_INDEX,
    ClusterCase,
    enrich_classification_batch_result_for_export,
    enrich_classification_session_result_for_export,
    format_classification_batch_output_for_detail,
    format_classification_output_for_detail,
)
from classification.lib import load_prompt as load_classification_prompt
from classification.lib import prompt_file_path as classification_prompt_file_path
from classification.templates import load_template
from clustering.cluster import run_clustering_with_repair
from clustering.lib import (
    MODULE_ROOT as CLUSTERING_MODULE_ROOT,
)
from clustering.lib import (
    audit_turn_coverage,
    enrich_clustering_result_for_export,
    format_clustering_output_for_detail,
)
from clustering.lib import (
    load_prompt as load_clustering_prompt,
)
from clustering.lib import (
    prompt_file_path as clustering_prompt_file_path,
)
from clustering.repair import (
    DEFAULT_REPAIR_PROMPT_VERSION,
    IncompleteTurnCoverageError,
    clustering_repair_prompt_file_path,
)
from common.case_paths import CONTEXT_CASES_INDEX, TRANSCRIPT_CASES_INDEX
from common.output_detail import normalize_output_detail
from common.prompts import normalize_prompt_version
from common.providers import (
    OPENAI_REASONING_EFFORT_ENV,
    ModelSpec,
    default_model_for_provider,
    normalize_provider_name,
    openai_model_supports_reasoning_effort,
)
from common.templates import DEFAULT_TEMPLATES_DIR
from common.transcripts import TranscriptCase, build_turn_catalog
from filtering.filter import run_filtering
from filtering.lib import (
    MODULE_ROOT as FILTERING_MODULE_ROOT,
)
from filtering.lib import (
    audit_drop_turn_ids,
    enrich_filtering_result_for_export,
    format_filtering_output_for_detail,
)
from filtering.lib import (
    load_prompt as load_filtering_prompt,
)
from filtering.lib import (
    prompt_file_path as filtering_prompt_file_path,
)
from generation.generate import run_generation_session
from generation.lib import (
    DEFAULT_SECTION_CONCURRENCY,
    ClusterAssignmentInput,
    enrich_generation_session_result_for_export,
    enrich_section_generation_result_for_export,
    format_generation_output_for_detail,
    format_section_output_for_detail,
    load_section_context_from_record,
)
from generation.lib import (
    load_prompt as load_generation_prompt,
)
from generation.lib import (
    prompt_file_path as generation_prompt_file_path,
)
from ui.bridge import (
    apply_filtering_to_transcript,
    clusters_from_clustering_result,
    drop_turn_ids_from_filtering_result,
)
from ui.discovery import AI_PIPELINE_ROOT

OUTPUT_DETAIL = "compact"


@dataclass(frozen=True, slots=True)
class StepConfig:
    provider: str
    model: str
    prompt_version: str
    openai_reasoning_effort: str | None = None


@contextmanager
def apply_step_config_env(config: StepConfig):
    env_keys = [OPENAI_REASONING_EFFORT_ENV]
    previous = {key: os.environ.get(key) for key in env_keys}
    try:
        if (
            config.openai_reasoning_effort is not None
            and normalize_provider_name(config.provider) == "openai"
            and openai_model_supports_reasoning_effort(config.model)
        ):
            os.environ[OPENAI_REASONING_EFFORT_ENV] = config.openai_reasoning_effort
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _step_config_metadata(config: StepConfig) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if (
        config.openai_reasoning_effort is not None
        and normalize_provider_name(config.provider) == "openai"
        and openai_model_supports_reasoning_effort(config.model)
    ):
        metadata["openai_reasoning_effort"] = config.openai_reasoning_effort
    return metadata


@dataclass(frozen=True, slots=True)
class PipelineRunOutput:
    step: str
    result_record: dict[str, object]
    output_path: Path


def load_env() -> None:
    load_dotenv(AI_PIPELINE_ROOT / ".env.local", override=False)


def build_model_spec(provider: str, model: str) -> ModelSpec:
    normalized_provider = normalize_provider_name(provider)
    resolved_model = (
        model.strip() or default_model_for_provider(normalized_provider)
    ).strip()
    return ModelSpec(
        alias=normalized_provider,
        provider=normalized_provider,
        model=resolved_model,
    )


def _persist_results(output_path: Path, payload: dict[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_filtering_step(
    *,
    case: TranscriptCase,
    config: StepConfig,
) -> PipelineRunOutput:
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    provider = model_spec.provider
    model = model_spec.model
    system_prompt = load_filtering_prompt(prompt_version)
    prompt_path = filtering_prompt_file_path(prompt_version)
    catalog = build_turn_catalog(case.transcript_json)
    run_started_at = datetime.now(UTC)
    results_dir = FILTERING_MODULE_ROOT / "results"
    output_path = (
        results_dir
        / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{case.id}_{provider}.json"
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        result, llm_response = run_filtering(
            case=case,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)
    drop_audit = audit_drop_turn_ids(result, catalog)
    output_payload = format_filtering_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "filtering_result": enrich_filtering_result_for_export(result, catalog),
            "drop_audit": drop_audit.to_dict(),
            "raw_response": llm_response.content,
        },
        output_detail,
    )
    result_record: dict[str, object] = {
        "run_mode": "debug",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "response_time_ms": response_time_ms,
        "llm_usage": llm_response.usage,
        "output_path": str(output_path),
        "case_id": case.id,
        "case_notes": case.notes,
        "cases_file": str(TRANSCRIPT_CASES_INDEX),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(FILTERING_MODULE_ROOT)),
        "output_detail": output_detail,
        "turn_count": len(catalog),
        **_step_config_metadata(config),
        **output_payload,
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="filtering",
        result_record=result_record,
        output_path=output_path,
    )


def run_clustering_step(
    *,
    case: TranscriptCase,
    config: StepConfig,
    require_complete_coverage: bool = False,
) -> PipelineRunOutput:
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    provider = model_spec.provider
    model = model_spec.model
    system_prompt = load_clustering_prompt(prompt_version)
    prompt_path = clustering_prompt_file_path(prompt_version)
    catalog = build_turn_catalog(case.transcript_json)
    run_started_at = datetime.now(UTC)
    results_dir = CLUSTERING_MODULE_ROOT / "results"
    output_path = (
        results_dir
        / f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_debug_{case.id}_{provider}.json"
    )

    repair_prompt_path = clustering_repair_prompt_file_path(
        DEFAULT_REPAIR_PROMPT_VERSION
    )

    with apply_step_config_env(config):
        started_at = time.perf_counter()
        session_run = run_clustering_with_repair(
            case=case,
            model_spec=model_spec,
            system_prompt=system_prompt,
            require_complete_coverage=require_complete_coverage,
        )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = session_run.result
    coverage = audit_turn_coverage(result, catalog)
    repair_passes = [repair_pass.to_dict() for repair_pass in session_run.repair_passes]
    output_payload = format_clustering_output_for_detail(
        {
            "provider": provider,
            "model": model,
            "clustering_result": enrich_clustering_result_for_export(result, catalog),
            "turn_coverage": coverage.to_dict(),
            "repair_passes": repair_passes,
            "raw_response": session_run.llm_response.content,
            "thinking": session_run.llm_response.thinking,
            "thinking_source": session_run.llm_response.thinking_source,
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
        "response_time_ms": response_time_ms,
        "llm_usage": session_run.llm_response.usage,
        "initial_response_time_ms": session_run.response_time_ms,
        "repair_response_time_ms": session_run.repair_response_time_ms,
        "repair_pass_count": len(repair_passes),
        "repair_prompt_version": DEFAULT_REPAIR_PROMPT_VERSION,
        "repair_prompt_file": str(
            repair_prompt_path.relative_to(CLUSTERING_MODULE_ROOT)
        ),
        "output_path": str(output_path),
        "case_id": case.id,
        "case_notes": case.notes,
        "cases_file": str(TRANSCRIPT_CASES_INDEX),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(CLUSTERING_MODULE_ROOT)),
        "output_detail": output_detail,
        "turn_count": len(catalog),
        **_step_config_metadata(config),
        **output_payload,
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="clustering",
        result_record=result_record,
        output_path=output_path,
    )


def run_classification_step(
    *,
    session_id: str,
    clusters: list[ClusterCase],
    template_id: str,
    config: StepConfig,
    clustering_result_file: str | None = None,
) -> PipelineRunOutput:
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    provider = model_spec.provider
    model = model_spec.model
    template = load_template(template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    system_prompt = load_classification_prompt(prompt_version)
    prompt_path = classification_prompt_file_path(prompt_version)
    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "classification" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_session_{session_id}_{provider}.json"
    )

    with apply_step_config_env(config):
        session_run = run_classification_session(
            session_id=session_id,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            input_token_budget=DEFAULT_INPUT_TOKEN_BUDGET,
            token_encoding=DEFAULT_TOKEN_ENCODING,
        )

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
            "batch_assignment_audit": batch_run.assignment_audit.to_dict(),
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
            "batch_assignment_audit": session_run.session_audit.to_dict(),
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
        "session_id": session_id,
        "cluster_count": len(clusters),
        "cases_file": str(DEFAULT_CASES_INDEX),
        "clustering_result_file": clustering_result_file or "",
        "template_id": template_id,
        "template_file": str(DEFAULT_TEMPLATES_DIR / f"{template_id}.json"),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(
            prompt_path.relative_to(AI_PIPELINE_ROOT / "classification")
        ),
        "output_detail": output_detail,
        "input_token_budget": DEFAULT_INPUT_TOKEN_BUDGET,
        "token_encoding": DEFAULT_TOKEN_ENCODING,
        **_step_config_metadata(config),
        **output_payload,
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="classification",
        result_record=result_record,
        output_path=output_path,
    )


def run_generation_step(
    *,
    session_id: str,
    clusters: list[ClusterCase],
    assignments: list[ClusterAssignmentInput],
    template_id: str,
    config: StepConfig,
    classification_result_file: str | None = None,
    clustering_result_file: str | None = None,
    claim_classification_result_file: str | None = None,
) -> PipelineRunOutput:
    output_detail = normalize_output_detail(OUTPUT_DETAIL)
    prompt_version = normalize_prompt_version(config.prompt_version)
    model_spec = build_model_spec(config.provider, config.model)
    provider = model_spec.provider
    model = model_spec.model
    template = load_template(template_id, templates_dir=DEFAULT_TEMPLATES_DIR)
    system_prompt = load_generation_prompt(prompt_version)
    prompt_path = generation_prompt_file_path(prompt_version)
    run_started_at = datetime.now(UTC)
    results_dir = AI_PIPELINE_ROOT / "generation" / "results"
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_session_{session_id}_{provider}.json"
    )

    section_context = None
    if claim_classification_result_file:
        section_context = load_section_context_from_record(
            Path(claim_classification_result_file)
        )

    with apply_step_config_env(config):
        session_run = run_generation_session(
            session_id=session_id,
            assignments=assignments,
            clusters=clusters,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            section_concurrency=DEFAULT_SECTION_CONCURRENCY,
            section_context=section_context,
        )

    cluster_ids_by_section = {
        section_run.section_id: section_run.cluster_ids
        for section_run in session_run.section_runs
    }
    context_present_by_section = {
        section_run.section_id: section_run.context_present
        for section_run in session_run.section_runs
    }
    context_chars_by_section = {
        section_run.section_id: section_run.context_chars
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
            "context_present": section_run.context_present,
            "context_chars": section_run.context_chars,
            "response_time_ms": section_run.response_time_ms,
            "generation_result": enrich_section_generation_result_for_export(
                section_run.result,
                heading=section.heading,
                cluster_ids=section_run.cluster_ids,
                context_present=section_run.context_present,
                context_chars=section_run.context_chars,
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
        context_present_by_section=context_present_by_section,
        context_chars_by_section=context_chars_by_section,
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
        "session_id": session_id,
        "cluster_count": len(clusters),
        "cases_file": str(DEFAULT_CASES_INDEX),
        "classification_result_file": classification_result_file or "",
        "claim_classification_result_file": claim_classification_result_file or "",
        "clustering_result_file": clustering_result_file or "",
        "template_id": template_id,
        "template_file": str(DEFAULT_TEMPLATES_DIR / f"{template_id}.json"),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(AI_PIPELINE_ROOT / "generation")),
        "output_detail": output_detail,
        **_step_config_metadata(config),
        **output_payload,
    }
    _persist_results(output_path, result_record)
    return PipelineRunOutput(
        step="generation",
        result_record=result_record,
        output_path=output_path,
    )


def assignments_from_classification_record(
    result_record: dict[str, object],
) -> list[ClusterAssignmentInput]:
    session_result = result_record.get("classification_session_result")
    if not isinstance(session_result, dict):
        raise ValueError("classification_session_result_missing")
    assignments_raw = session_result.get("assignments")
    if not isinstance(assignments_raw, list):
        raise ValueError("classification_assignments_missing")
    assignments: list[ClusterAssignmentInput] = []
    for index, item in enumerate(assignments_raw):
        if not isinstance(item, dict):
            raise ValueError(f"classification_assignment_{index}_must_be_object")
        cluster_id = item.get("cluster_id")
        section_ids = item.get("section_ids")
        if not isinstance(cluster_id, str):
            raise ValueError(f"classification_assignment_{index}_cluster_id_missing")
        if not isinstance(section_ids, list):
            raise ValueError(f"classification_assignment_{index}_section_ids_missing")
        assignments.append(
            ClusterAssignmentInput(
                cluster_id=cluster_id,
                section_ids=[str(section_id) for section_id in section_ids],
            )
        )
    return assignments


def transcript_case_from_filtering_result(
    *,
    base_case: TranscriptCase,
    filtering_record: dict[str, object],
) -> TranscriptCase:
    drop_ids = drop_turn_ids_from_filtering_result(filtering_record)
    filtered_json = apply_filtering_to_transcript(base_case.transcript_json, drop_ids)
    return TranscriptCase(
        id=base_case.id,
        transcript_json=filtered_json,
        notes=base_case.notes,
    )


from ui.context_runner import (
    run_context_ad_hoc_pipeline_step,
    run_context_classify_clusters_step,
    run_context_cluster_spans_step,
    run_context_filter_spans_step,
    run_context_pipeline_step,
    run_context_section_adapter_step,
    run_context_triage_step,
)

def run_e2e_pipeline(
    *,
    case_id: str,
    session_id: str,
    template_id: str,
    filtering_config: StepConfig,
    clustering_config: StepConfig,
    classification_config: StepConfig,
    generation_config: StepConfig,
    base_case: TranscriptCase | None = None,
    context_case_id: str | None = None,
    context_config: StepConfig | None = None,
    include_doctor_note: bool = True,
    include_documents: bool = True,
) -> list[PipelineRunOutput]:
    from ui.discovery import load_transcript_case

    resolved_case = base_case or load_transcript_case(case_id)
    outputs: list[PipelineRunOutput] = []

    filtering_output = run_filtering_step(case=resolved_case, config=filtering_config)
    outputs.append(filtering_output)

    clustering_case = transcript_case_from_filtering_result(
        base_case=resolved_case,
        filtering_record=filtering_output.result_record,
    )
    clustering_output = run_clustering_step(
        case=clustering_case,
        config=clustering_config,
        require_complete_coverage=True,
    )
    outputs.append(clustering_output)

    clusters = clusters_from_clustering_result(
        clustering_output.result_record,
        session_id=session_id,
        template_id=template_id,
    )
    classification_output = run_classification_step(
        session_id=session_id,
        clusters=clusters,
        template_id=template_id,
        config=classification_config,
        clustering_result_file=str(clustering_output.output_path),
    )
    outputs.append(classification_output)

    assignments = assignments_from_classification_record(
        classification_output.result_record
    )

    claim_classification_result_file: str | None = None
    if context_case_id and context_config is not None:
        context_output = run_context_pipeline_step(
            context_case_id=context_case_id,
            config=context_config,
            include_doctor_note=include_doctor_note,
            include_documents=include_documents,
        )
        outputs.append(context_output)
        claim_classification_result_file = str(context_output.output_path)

    generation_output = run_generation_step(
        session_id=session_id,
        clusters=clusters,
        assignments=assignments,
        template_id=template_id,
        config=generation_config,
        classification_result_file=str(classification_output.output_path),
        clustering_result_file=str(clustering_output.output_path),
        claim_classification_result_file=claim_classification_result_file,
    )
    outputs.append(generation_output)
    return outputs


__all__ = [
    "IncompleteTurnCoverageError",
    "PipelineRunOutput",
    "StepConfig",
    "assignments_from_classification_record",
    "build_model_spec",
    "load_env",
    "run_classification_step",
    "run_clustering_step",
    "run_context_ad_hoc_pipeline_step",
    "run_context_classify_clusters_step",
    "run_context_cluster_spans_step",
    "run_context_filter_spans_step",
    "run_context_pipeline_step",
    "run_context_section_adapter_step",
    "run_context_triage_step",
    "run_e2e_pipeline",
    "run_generation_step",
    "run_filtering_step",
    "transcript_case_from_filtering_result",
]
