from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from classification.batching import (
    DEFAULT_BATCH_CONCURRENCY,
    DEFAULT_INPUT_TOKEN_BUDGET,
    DEFAULT_TOKEN_ENCODING,
    BatchPlan,
    ClassificationBatch,
    plan_balanced_batches,
)
from classification.lib import (
    BatchAssignmentAudit,
    ClassificationBatchResult,
    ClassificationResult,
    ClassificationSessionResult,
    ClusterCase,
    audit_batch_assignments,
    audit_section_ids,
    audit_session_result,
    classification_output_schema,
    merge_batch_results,
    parse_classification_batch_result,
    parse_classification_result,
    prepare_classification_prompts,
    render_classification_batch_payload,
    render_classification_user_payload,
)
from classification.templates import ClassificationTemplate
from common.llm_response import LlmResponse, summarize_llm_responses
from common.providers import ModelSpec, call_llm, call_llm_detailed


@dataclass(frozen=True, slots=True)
class ClassificationBatchRun:
    batch_index: int
    clusters: list[ClusterCase]
    result: ClassificationBatchResult
    llm_response: LlmResponse
    raw_response: str
    assignment_audit: BatchAssignmentAudit
    response_time_ms: int

    @property
    def thinking(self) -> str | None:
        return self.llm_response.thinking

    @property
    def thinking_source(self) -> str | None:
        return self.llm_response.thinking_source

    @property
    def llm_usage(self) -> dict[str, object]:
        return self.llm_response.usage

    @property
    def llm_request_params(self) -> dict[str, object]:
        return self.llm_response.request_params


@dataclass(frozen=True, slots=True)
class ClassificationSessionRun:
    session_id: str
    batch_plan: BatchPlan
    batch_runs: list[ClassificationBatchRun]
    session_result: ClassificationSessionResult
    session_audit: BatchAssignmentAudit
    total_response_time_ms: int
    sum_batch_response_time_ms: int
    batch_execution_mode: str
    batch_concurrency: int
    llm_usage_summary: dict[str, object]


def resolve_batch_concurrency(raw: int | None = None) -> int:
    if raw is not None:
        return max(0, raw)
    env_value = os.environ.get(
        "CLASSIFICATION_BATCH_CONCURRENCY",
        str(DEFAULT_BATCH_CONCURRENCY),
    ).strip()
    if not env_value:
        return DEFAULT_BATCH_CONCURRENCY
    return max(0, int(env_value))


def run_classification(
    *,
    cluster_case: ClusterCase,
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v002",
) -> tuple[ClassificationResult, str]:
    resolved_system_prompt, _ = prepare_classification_prompts(
        system_prompt,
        template,
        prompt_version=prompt_version,
    )
    user_payload = render_classification_user_payload(
        cluster_case=cluster_case,
        template=template,
        prompt_version=prompt_version,
    )
    output_schema = classification_output_schema(
        template,
        prompt_version=prompt_version,
    )
    raw_response = call_llm(
        provider=model_spec.provider,
        model=model_spec.model,
        system=resolved_system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    result = parse_classification_result(raw_response)
    section_audit = audit_section_ids(result, template)
    if section_audit.unknown_section_ids:
        unknown = section_audit.unknown_section_ids[0]
        raise ValueError(f"classification_unknown_section_id: {unknown!r}")
    if section_audit.duplicate_section_ids:
        duplicate = section_audit.duplicate_section_ids[0]
        raise ValueError(f"classification_duplicate_section_id: {duplicate!r}")
    return result, raw_response


def run_classification_batch(
    *,
    clusters: list[ClusterCase],
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v002",
) -> tuple[ClassificationBatchResult, LlmResponse, int]:
    if not clusters:
        raise ValueError("classification_batch_requires_at_least_one_cluster")

    resolved_system_prompt, _ = prepare_classification_prompts(
        system_prompt,
        template,
        prompt_version=prompt_version,
    )
    user_payload = render_classification_batch_payload(
        clusters=clusters,
        template=template,
        prompt_version=prompt_version,
    )
    output_schema = classification_output_schema(
        template,
        prompt_version=prompt_version,
    )
    started_at = time.perf_counter()
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=resolved_system_prompt,
        user=user_payload,
        output_schema=output_schema,
    )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = parse_classification_batch_result(llm_response.content)
    expected_cluster_ids = [cluster.id for cluster in clusters]
    assignment_audit = audit_batch_assignments(
        result,
        expected_cluster_ids,
        template,
    )
    if assignment_audit.missing_cluster_ids:
        missing = assignment_audit.missing_cluster_ids[0]
        raise ValueError(f"classification_missing_cluster_id: {missing!r}")
    if assignment_audit.extra_cluster_ids:
        extra = assignment_audit.extra_cluster_ids[0]
        raise ValueError(f"classification_extra_cluster_id: {extra!r}")
    if assignment_audit.duplicate_cluster_ids:
        duplicate = assignment_audit.duplicate_cluster_ids[0]
        raise ValueError(f"classification_duplicate_cluster_id: {duplicate!r}")
    if assignment_audit.invalid_section_cluster_ids:
        invalid = assignment_audit.invalid_section_cluster_ids[0]
        raise ValueError(f"classification_invalid_section_ids: {invalid!r}")
    return result, llm_response, response_time_ms


def _run_classification_batch_job(
    batch: ClassificationBatch,
    *,
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
) -> ClassificationBatchRun:
    result, llm_response, response_time_ms = run_classification_batch(
        clusters=batch.clusters,
        template=template,
        model_spec=model_spec,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
    )
    assignment_audit = audit_batch_assignments(
        result,
        [cluster.id for cluster in batch.clusters],
        template,
    )
    return ClassificationBatchRun(
        batch_index=batch.batch_index,
        clusters=batch.clusters,
        result=result,
        llm_response=llm_response,
        raw_response=llm_response.content,
        assignment_audit=assignment_audit,
        response_time_ms=response_time_ms,
    )


def _run_batches_sequential(
    batches: list[ClassificationBatch],
    *,
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
) -> list[ClassificationBatchRun]:
    return [
        _run_classification_batch_job(
            batch,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
        )
        for batch in batches
    ]


def _run_batches_parallel(
    batches: list[ClassificationBatch],
    *,
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    batch_concurrency: int,
) -> list[ClassificationBatchRun]:
    max_workers = (
        len(batches)
        if batch_concurrency == 0
        else min(len(batches), batch_concurrency)
    )
    batch_runs_by_index: dict[int, ClassificationBatchRun] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_classification_batch_job,
                batch,
                template=template,
                model_spec=model_spec,
                system_prompt=system_prompt,
                prompt_version=prompt_version,
            ): batch.batch_index
            for batch in batches
        }
        for future in as_completed(futures):
            batch_run = future.result()
            batch_runs_by_index[batch_run.batch_index] = batch_run
    return [batch_runs_by_index[index] for index in sorted(batch_runs_by_index)]


def run_classification_session(
    *,
    session_id: str,
    clusters: list[ClusterCase],
    template: ClassificationTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v002",
    input_token_budget: int = DEFAULT_INPUT_TOKEN_BUDGET,
    token_encoding: str = DEFAULT_TOKEN_ENCODING,
    batch_concurrency: int | None = None,
) -> ClassificationSessionRun:
    if not clusters:
        raise ValueError("classification_session_requires_at_least_one_cluster")

    resolved_concurrency = resolve_batch_concurrency(batch_concurrency)
    batch_plan = plan_balanced_batches(
        clusters,
        template,
        budget=input_token_budget,
        encoding_name=token_encoding,
        prompt_version=prompt_version,
        base_system_prompt=system_prompt,
    )
    use_parallel = len(batch_plan.batches) > 1 and resolved_concurrency != 1
    batch_execution_mode = "parallel" if use_parallel else "sequential"

    started_at = time.perf_counter()
    if use_parallel:
        batch_runs = _run_batches_parallel(
            batch_plan.batches,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            batch_concurrency=resolved_concurrency,
        )
    else:
        batch_runs = _run_batches_sequential(
            batch_plan.batches,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
        )
    total_response_time_ms = int((time.perf_counter() - started_at) * 1000)

    batch_results = [batch_run.result for batch_run in batch_runs]
    llm_responses = [batch_run.llm_response for batch_run in batch_runs]
    sum_batch_response_time_ms = sum(
        batch_run.response_time_ms for batch_run in batch_runs
    )
    session_result = merge_batch_results(batch_results)
    session_audit = audit_session_result(
        session_result,
        [cluster.id for cluster in clusters],
        template,
    )
    llm_usage_summary = summarize_llm_responses(llm_responses)
    llm_usage_summary = {
        **llm_usage_summary,
        "batch_execution_mode": batch_execution_mode,
        "batch_concurrency": resolved_concurrency,
        "sum_batch_response_time_ms": sum_batch_response_time_ms,
    }
    return ClassificationSessionRun(
        session_id=session_id,
        batch_plan=batch_plan,
        batch_runs=batch_runs,
        session_result=session_result,
        session_audit=session_audit,
        total_response_time_ms=total_response_time_ms,
        sum_batch_response_time_ms=sum_batch_response_time_ms,
        batch_execution_mode=batch_execution_mode,
        batch_concurrency=resolved_concurrency,
        llm_usage_summary=llm_usage_summary,
    )
