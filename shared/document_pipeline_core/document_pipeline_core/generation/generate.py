from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from document_pipeline_core.classification.lib import ClusterCase
from document_pipeline_core.common.context_spans import Directive, SectionContext, SectionEvidence
from document_pipeline_core.common.llm_response import LlmResponse, summarize_llm_responses
from document_pipeline_core.common.providers import ModelSpec, call_llm_detailed
from document_pipeline_core.common.templates import ClinicalTemplate
from document_pipeline_core.generation.evidence_markers import audit_evidence_markers
from document_pipeline_core.generation.lib import (
    DEFAULT_CLUSTER_PLANNER_CONCURRENCY,
    DEFAULT_SECTION_CONCURRENCY,
    GENERATION_ROUTE_CLUSTER_PLANNER,
    GENERATION_ROUTE_DIRECT,
    GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
    GENERATION_ROUTE_TWO_STEP,
    ClusterAssignmentInput,
    GenerationSessionResult,
    GenerationValidationError,
    SectionGenerationJob,
    SectionGenerationPlan,
    SectionGenerationResult,
    cluster_planner_run_to_export,
    cluster_planner_runs_have_planned_items,
    cluster_topic_label,
    collect_allowed_evidence_id_set,
    collect_cluster_allowed_evidence_id_set,
    generation_cluster_planner_output_schema,
    generation_direct_output_schema,
    generation_direct_uses_py_prompt,
    generation_direct_with_evidence_output_schema,
    generation_planner_output_schema,
    generation_prompt_files_for_route,
    load_generation_cluster_planner_prompt,
    load_generation_cluster_renderer_prompt,
    load_generation_direct_with_evidence_prompt,
    load_generation_planner_prompt,
    load_generation_renderer_prompt,
    normalize_section_generation_content,
    parse_linked_content,
    parse_planner_items_result,
    parse_section_generation_result,
    plan_section_generation,
    planner_items_to_export,
    render_cluster_planner_payload,
    render_cluster_renderer_payload,
    render_combined_cluster_plans_block,
    render_direct_payload,
    render_direct_with_evidence_payload,
    render_planned_items_block,
    render_planner_payload,
    render_renderer_payload,
    render_section_user_payload,
    resolve_generation_route,
    resolve_section_generation_route,
)

_OPENAI_EMPTY_RESPONSE = "ai_pipeline_openai_empty_response"


def _job_diagnostics_kwargs(
    job: SectionGenerationJob,
    *,
    generation_route: str,
    generation_substep: str,
    prompt_version: str,
) -> dict[str, object]:
    return {
        "section_id": job.section_id,
        "section_heading": job.section.heading,
        "generation_route": generation_route,
        "generation_substep": generation_substep,
        "cluster_ids": job.cluster_ids,
        "context_present": job.context_present,
        "context_chars": job.context_chars,
        "prompt_version": prompt_version,
    }


def _retry_count_from_response(llm_response: LlmResponse | None) -> int | None:
    if llm_response is None:
        return None
    retry_count = llm_response.request_params.get("retry_count")
    if isinstance(retry_count, int):
        return retry_count
    return None


def _raise_generation_error(
    exc: BaseException,
    *,
    job: SectionGenerationJob,
    generation_route: str,
    generation_substep: str,
    prompt_version: str,
    llm_response: LlmResponse | None = None,
    allowed_evidence_ids: set[str] | None = None,
    planner_items: list[dict[str, object]] | None = None,
    planned_items_block: str | None = None,
    planner_response: str | None = None,
    cluster_id: str | None = None,
) -> None:
    if isinstance(exc, GenerationValidationError):
        raise exc
    kwargs = _job_diagnostics_kwargs(
        job,
        generation_route=generation_route,
        generation_substep=generation_substep,
        prompt_version=prompt_version,
    )
    if cluster_id is not None:
        kwargs["cluster_id"] = cluster_id
    if llm_response is not None:
        kwargs["raw_response"] = llm_response.content
        retry_count = _retry_count_from_response(llm_response)
        if retry_count is not None:
            kwargs["retry_count"] = retry_count
    if allowed_evidence_ids is not None:
        kwargs["allowed_evidence_ids"] = sorted(allowed_evidence_ids)
        kwargs["evidence_count"] = len(job.evidence_spans)
    if planner_items is not None:
        kwargs["planner_items"] = planner_items
    if planned_items_block is not None:
        kwargs["planned_items_block"] = planned_items_block
    if planner_response is not None:
        kwargs["planner_response"] = planner_response
    partial_response = getattr(exc, "partial_content", None)
    if isinstance(partial_response, str) and partial_response:
        kwargs["partial_response"] = partial_response
    partial_thinking = getattr(exc, "partial_thinking", None)
    if isinstance(partial_thinking, str) and partial_thinking:
        kwargs["partial_thinking"] = partial_thinking
    output_item_types = getattr(exc, "output_item_types", None)
    if isinstance(output_item_types, list) and output_item_types:
        kwargs["response_output_item_types"] = output_item_types
    message_statuses = getattr(exc, "message_statuses", None)
    if isinstance(message_statuses, list) and message_statuses:
        kwargs["response_message_statuses"] = message_statuses
    response_status = getattr(exc, "response_status", None)
    if isinstance(response_status, str):
        kwargs["response_status"] = response_status
    response_error = getattr(exc, "response_error", None)
    if isinstance(response_error, dict) and response_error:
        kwargs["response_error"] = response_error
    response_incomplete_details = getattr(exc, "response_incomplete_details", None)
    if isinstance(response_incomplete_details, dict) and response_incomplete_details:
        kwargs["response_incomplete_details"] = response_incomplete_details
    raise GenerationValidationError(str(exc), **kwargs) from exc


def call_generation_llm_detailed(
    *,
    provider: str,
    model: str,
    system: str,
    user: str,
    output_schema: dict[str, object] | None = None,
    json_mode: bool | None = None,
) -> LlmResponse:
    try:
        return call_llm_detailed(
            provider=provider,
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            json_mode=json_mode,
        )
    except ValueError as exc:
        if provider != "openai" or str(exc) != _OPENAI_EMPTY_RESPONSE:
            raise
        retry_response = call_llm_detailed(
            provider=provider,
            model=model,
            system=system,
            user=user,
            output_schema=output_schema,
            json_mode=json_mode,
        )
        request_params = dict(retry_response.request_params)
        request_params["retry_count"] = 1
        return LlmResponse(
            content=retry_response.content,
            thinking=retry_response.thinking,
            thinking_source=retry_response.thinking_source,
            usage=retry_response.usage,
            request_params=request_params,
            timing=retry_response.timing,
        )


@dataclass(frozen=True, slots=True)
class SectionGenerationRun:
    section_id: str
    cluster_ids: list[str]
    context_present: bool
    context_chars: int
    result: SectionGenerationResult
    llm_responses: list[LlmResponse]
    raw_response: str
    response_time_ms: int
    generation_route: str = "legacy"
    planner_items: list[dict[str, object]] | None = None
    planned_items_block: str | None = None
    cluster_planner_runs: list[dict[str, object]] | None = None
    combined_cluster_plans_block: str | None = None
    renderer_raw_response: str | None = None
    renderer_skipped: bool = False
    prompt_files: dict[str, str] | None = None

    @property
    def llm_response(self) -> LlmResponse:
        return self.llm_responses[-1]

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
class GenerationSessionRun:
    session_id: str
    section_plan: SectionGenerationPlan
    section_runs: list[SectionGenerationRun]
    session_result: GenerationSessionResult
    total_response_time_ms: int
    sum_section_response_time_ms: int
    section_execution_mode: str
    section_concurrency: int
    llm_usage_summary: dict[str, object]


def resolve_section_concurrency(raw: int | None = None) -> int:
    if raw is not None:
        return max(0, raw)
    env_value = os.environ.get(
        "GENERATION_SECTION_CONCURRENCY",
        str(DEFAULT_SECTION_CONCURRENCY),
    ).strip()
    if not env_value:
        return DEFAULT_SECTION_CONCURRENCY
    return max(0, int(env_value))


def resolve_cluster_planner_concurrency(raw: int | None = None) -> int:
    if raw is not None:
        return max(0, raw)
    env_value = os.environ.get(
        "GENERATION_CLUSTER_PLANNER_CONCURRENCY",
        str(DEFAULT_CLUSTER_PLANNER_CONCURRENCY),
    ).strip()
    if not env_value:
        return DEFAULT_CLUSTER_PLANNER_CONCURRENCY
    return max(0, int(env_value))


@dataclass(frozen=True, slots=True)
class _ClusterPlannerSubrun:
    cluster_id: str
    export: dict[str, object]
    llm_response: LlmResponse


def _run_single_cluster_planner(
    *,
    cluster: ClusterCase,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    prompt_version: str,
    planner_system: str,
) -> _ClusterPlannerSubrun:
    allowed_ids = collect_cluster_allowed_evidence_id_set(cluster)
    planner_payload = render_cluster_planner_payload(
        job=job,
        template=template,
        cluster=cluster,
        prompt_version=prompt_version,
    )
    planner_schema = generation_cluster_planner_output_schema(
        allowed_evidence_ids=sorted(allowed_ids),
        prompt_version=prompt_version,
    )
    cluster_started_at = time.perf_counter()
    planner_response: LlmResponse | None = None
    try:
        planner_response = call_generation_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=planner_system,
            user=planner_payload,
            output_schema=planner_schema,
        )
        planner_result = parse_planner_items_result(
            planner_response.content,
            allowed_evidence_ids=allowed_ids,
        )
    except Exception as exc:
        _raise_generation_error(
            exc,
            job=job,
            generation_route=GENERATION_ROUTE_CLUSTER_PLANNER,
            generation_substep="cluster_planner",
            prompt_version=prompt_version,
            llm_response=planner_response,
            allowed_evidence_ids=allowed_ids,
            cluster_id=cluster.id,
        )
    planned_block = render_planned_items_block(planner_result.items)
    exported_items = planner_items_to_export(planner_result.items)
    cluster_response_time_ms = int((time.perf_counter() - cluster_started_at) * 1000)
    export = cluster_planner_run_to_export(
        cluster_id=cluster.id,
        topic_label=cluster_topic_label(cluster),
        planner_items=exported_items,
        planned_items_block=planned_block,
        llm_response=planner_response,
        response_time_ms=cluster_response_time_ms,
    )
    return _ClusterPlannerSubrun(
        cluster_id=cluster.id,
        export=export,
        llm_response=planner_response,
    )


def _run_cluster_planner_subruns(
    *,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    prompt_version: str,
    planner_system: str,
    cluster_planner_concurrency: int,
) -> list[_ClusterPlannerSubrun]:
    clusters = job.clusters
    if not clusters:
        return []
    if len(clusters) == 1 or cluster_planner_concurrency == 1:
        return [
            _run_single_cluster_planner(
                cluster=cluster,
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version=prompt_version,
                planner_system=planner_system,
            )
            for cluster in clusters
        ]

    max_workers = (
        len(clusters)
        if cluster_planner_concurrency == 0
        else min(len(clusters), cluster_planner_concurrency)
    )
    runs_by_cluster_id: dict[str, _ClusterPlannerSubrun] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single_cluster_planner,
                cluster=cluster,
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version=prompt_version,
                planner_system=planner_system,
            ): cluster.id
            for cluster in clusters
        }
        for future in as_completed(futures):
            subrun = future.result()
            runs_by_cluster_id[subrun.cluster_id] = subrun
    return [runs_by_cluster_id[cluster.id] for cluster in clusters]


def run_section_generation(
    *,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v003",
    linked_evidence_two_step: bool = False,
    generation_route: str | None = None,
    cluster_planner_concurrency: int | None = None,
) -> tuple[
    SectionGenerationResult,
    list[LlmResponse],
    int,
    str,
    list[dict[str, object]] | None,
    str | None,
    list[dict[str, object]] | None,
    str | None,
    str | None,
    dict[str, str] | None,
    bool,
]:
    session_route = resolve_generation_route(
        generation_route=generation_route,
        linked_evidence_two_step=linked_evidence_two_step,
    )
    section_route = resolve_section_generation_route(
        requested_route=session_route,
        section=job.section,
    )
    prompt_files = generation_prompt_files_for_route(section_route, prompt_version)

    if generation_direct_uses_py_prompt(prompt_version):
        if section_route == GENERATION_ROUTE_CLUSTER_PLANNER:
            return run_cluster_planner_section_generation(
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version=prompt_version,
                prompt_files=prompt_files,
                cluster_planner_concurrency=cluster_planner_concurrency,
            )
        if section_route == GENERATION_ROUTE_TWO_STEP:
            result, responses, ms, route, items, block = (
                run_two_step_section_generation(
                    job=job,
                    template=template,
                    model_spec=model_spec,
                    prompt_version=prompt_version,
                )
            )
            return (
                result,
                responses,
                ms,
                route,
                items,
                block,
                None,
                None,
                None,
                prompt_files,
                False,
            )
        if section_route == GENERATION_ROUTE_DIRECT_WITH_EVIDENCE:
            evidence_system = load_generation_direct_with_evidence_prompt(
                prompt_version
            )
            user_payload = render_direct_with_evidence_payload(
                job,
                template,
                prompt_version=prompt_version,
            )
            output_schema = generation_direct_with_evidence_output_schema(
                section_id=job.section_id,
                prompt_version=prompt_version,
            )
            allowed_ids = collect_allowed_evidence_id_set(job)
            started_at = time.perf_counter()
            llm_response: LlmResponse | None = None
            try:
                llm_response = call_generation_llm_detailed(
                    provider=model_spec.provider,
                    model=model_spec.model,
                    system=evidence_system,
                    user=user_payload,
                    output_schema=output_schema,
                )
                result = parse_section_generation_result(
                    llm_response.content,
                    expected_section_id=job.section_id,
                )
                normalized_content = normalize_section_generation_content(
                    result.content,
                    heading=job.section.heading,
                )
                audit_evidence_markers(normalized_content, allowed_ids)
                result = result.model_copy(update={"content": normalized_content})
            except Exception as exc:
                _raise_generation_error(
                    exc,
                    job=job,
                    generation_route=GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
                    generation_substep="direct_with_evidence",
                    prompt_version=prompt_version,
                    llm_response=llm_response,
                    allowed_evidence_ids=allowed_ids,
                )
            response_time_ms = int((time.perf_counter() - started_at) * 1000)
            return (
                result,
                [llm_response],
                response_time_ms,
                GENERATION_ROUTE_DIRECT_WITH_EVIDENCE,
                None,
                None,
                None,
                None,
                None,
                prompt_files,
                False,
            )
        user_payload = render_direct_payload(
            job, template, prompt_version=prompt_version
        )
        output_schema = generation_direct_output_schema(
            section_id=job.section_id,
            prompt_version=prompt_version,
        )
        started_at = time.perf_counter()
        llm_response: LlmResponse | None = None
        try:
            llm_response = call_generation_llm_detailed(
                provider=model_spec.provider,
                model=model_spec.model,
                system=system_prompt,
                user=user_payload,
                output_schema=output_schema,
            )
            result = parse_section_generation_result(
                llm_response.content,
                expected_section_id=job.section_id,
            )
            result = result.model_copy(
                update={
                    "content": normalize_section_generation_content(
                        result.content,
                        heading=job.section.heading,
                    )
                }
            )
        except Exception as exc:
            _raise_generation_error(
                exc,
                job=job,
                generation_route="direct",
                generation_substep="direct",
                prompt_version=prompt_version,
                llm_response=llm_response,
            )
        response_time_ms = int((time.perf_counter() - started_at) * 1000)
        return (
            result,
            [llm_response],
            response_time_ms,
            GENERATION_ROUTE_DIRECT,
            None,
            None,
            None,
            None,
            None,
            prompt_files,
            False,
        )

    user_payload = render_section_user_payload(
        section=job.section,
        clusters=job.clusters,
        context=job.context,
        template=template,
    )
    started_at = time.perf_counter()
    llm_response: LlmResponse | None = None
    try:
        llm_response = call_generation_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=system_prompt,
            user=user_payload,
        )
        result = parse_section_generation_result(
            llm_response.content,
            expected_section_id=job.section_id,
        )
        result = result.model_copy(
            update={
                "content": normalize_section_generation_content(
                    result.content,
                    heading=job.section.heading,
                )
            }
        )
    except Exception as exc:
        _raise_generation_error(
            exc,
            job=job,
            generation_route="legacy",
            generation_substep="direct",
            prompt_version=prompt_version,
            llm_response=llm_response,
        )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    return (
        result,
        [llm_response],
        response_time_ms,
        "legacy",
        None,
        None,
        None,
        None,
        None,
        None,
        False,
    )


def run_two_step_section_generation(
    *,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    prompt_version: str,
) -> tuple[
    SectionGenerationResult,
    list[LlmResponse],
    int,
    str,
    list[dict[str, object]],
    str,
]:
    allowed_ids = collect_allowed_evidence_id_set(job)
    planner_system = load_generation_planner_prompt(prompt_version)
    planner_payload = render_planner_payload(
        job, template, prompt_version=prompt_version
    )
    planner_schema = generation_planner_output_schema(
        allowed_evidence_ids=sorted(allowed_ids),
        prompt_version=prompt_version,
    )
    started_at = time.perf_counter()
    planner_response: LlmResponse | None = None
    try:
        planner_response = call_generation_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=planner_system,
            user=planner_payload,
            output_schema=planner_schema,
        )
        planner_result = parse_planner_items_result(
            planner_response.content,
            allowed_evidence_ids=allowed_ids,
        )
    except Exception as exc:
        _raise_generation_error(
            exc,
            job=job,
            generation_route="two_step",
            generation_substep="planner",
            prompt_version=prompt_version,
            llm_response=planner_response,
            allowed_evidence_ids=allowed_ids,
        )
    planned_block = render_planned_items_block(planner_result.items)
    exported_items = planner_items_to_export(planner_result.items)

    renderer_system = load_generation_renderer_prompt(prompt_version)
    renderer_payload = render_renderer_payload(
        job,
        template,
        prompt_version=prompt_version,
        planned_items_block=planned_block,
    )
    renderer_response: LlmResponse | None = None
    try:
        renderer_response = call_generation_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=renderer_system,
            user=renderer_payload,
            json_mode=False,
        )
        content = parse_linked_content(renderer_response.content)
        content = normalize_section_generation_content(
            content,
            heading=job.section.heading,
        )
        audit_evidence_markers(content, allowed_ids)
        result = SectionGenerationResult(
            section_id=job.section_id,
            content=content,
        )
    except Exception as exc:
        _raise_generation_error(
            exc,
            job=job,
            generation_route="two_step",
            generation_substep="renderer",
            prompt_version=prompt_version,
            llm_response=renderer_response,
            planner_items=exported_items,
            planned_items_block=planned_block,
            planner_response=planner_response.content if planner_response else None,
        )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    return (
        result,
        [planner_response, renderer_response],
        response_time_ms,
        GENERATION_ROUTE_TWO_STEP,
        exported_items,
        planned_block,
    )


def run_cluster_planner_section_generation(
    *,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    prompt_version: str,
    prompt_files: dict[str, str] | None = None,
    cluster_planner_concurrency: int | None = None,
) -> tuple[
    SectionGenerationResult,
    list[LlmResponse],
    int,
    str,
    list[dict[str, object]] | None,
    str | None,
    list[dict[str, object]] | None,
    str | None,
    str | None,
    dict[str, str] | None,
    bool,
]:
    started_at = time.perf_counter()
    planner_system = load_generation_cluster_planner_prompt(prompt_version)
    resolved_cluster_concurrency = resolve_cluster_planner_concurrency(
        cluster_planner_concurrency
    )
    subruns = _run_cluster_planner_subruns(
        job=job,
        template=template,
        model_spec=model_spec,
        prompt_version=prompt_version,
        planner_system=planner_system,
        cluster_planner_concurrency=resolved_cluster_concurrency,
    )
    cluster_planner_runs = [subrun.export for subrun in subruns]
    llm_responses = [subrun.llm_response for subrun in subruns]

    combined_cluster_plans_block = render_combined_cluster_plans_block(
        cluster_planner_runs
    )
    has_planned_items = cluster_planner_runs_have_planned_items(cluster_planner_runs)
    resolved_prompt_files = prompt_files or generation_prompt_files_for_route(
        GENERATION_ROUTE_CLUSTER_PLANNER,
        prompt_version,
    )

    if not has_planned_items and not job.context_present:
        result = SectionGenerationResult(section_id=job.section_id, content="")
        response_time_ms = int((time.perf_counter() - started_at) * 1000)
        return (
            result,
            llm_responses,
            response_time_ms,
            GENERATION_ROUTE_CLUSTER_PLANNER,
            None,
            None,
            cluster_planner_runs,
            combined_cluster_plans_block,
            None,
            resolved_prompt_files,
            True,
        )

    renderer_system = load_generation_cluster_renderer_prompt(prompt_version)
    renderer_payload = render_cluster_renderer_payload(
        job,
        template,
        prompt_version=prompt_version,
        cluster_plans_block=combined_cluster_plans_block,
    )
    allowed_ids = collect_allowed_evidence_id_set(job)
    renderer_response: LlmResponse | None = None
    try:
        renderer_response = call_generation_llm_detailed(
            provider=model_spec.provider,
            model=model_spec.model,
            system=renderer_system,
            user=renderer_payload,
            json_mode=False,
        )
        content = parse_linked_content(renderer_response.content)
        content = normalize_section_generation_content(
            content,
            heading=job.section.heading,
        )
        audit_evidence_markers(content, allowed_ids)
        result = SectionGenerationResult(
            section_id=job.section_id,
            content=content,
        )
    except Exception as exc:
        _raise_generation_error(
            exc,
            job=job,
            generation_route=GENERATION_ROUTE_CLUSTER_PLANNER,
            generation_substep="cluster_renderer",
            prompt_version=prompt_version,
            llm_response=renderer_response,
            planned_items_block=combined_cluster_plans_block,
            allowed_evidence_ids=allowed_ids,
        )
    llm_responses.append(renderer_response)
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    return (
        result,
        llm_responses,
        response_time_ms,
        GENERATION_ROUTE_CLUSTER_PLANNER,
        None,
        None,
        cluster_planner_runs,
        combined_cluster_plans_block,
        renderer_response.content,
        resolved_prompt_files,
        False,
    )


def _run_section_generation_job(
    job: SectionGenerationJob,
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    linked_evidence_two_step: bool,
    generation_route: str | None = None,
    cluster_planner_concurrency: int | None = None,
) -> SectionGenerationRun:
    (
        result,
        llm_responses,
        response_time_ms,
        resolved_generation_route,
        planner_items,
        planned_block,
        cluster_planner_runs,
        combined_cluster_plans_block,
        renderer_raw_response,
        prompt_files,
        renderer_skipped,
    ) = run_section_generation(
        job=job,
        template=template,
        model_spec=model_spec,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        linked_evidence_two_step=linked_evidence_two_step,
        generation_route=generation_route,
        cluster_planner_concurrency=cluster_planner_concurrency,
    )
    raw_response = "" if renderer_skipped else llm_responses[-1].content
    return SectionGenerationRun(
        section_id=job.section_id,
        cluster_ids=job.cluster_ids,
        context_present=job.context_present,
        context_chars=job.context_chars,
        result=result,
        llm_responses=llm_responses,
        raw_response=raw_response,
        response_time_ms=response_time_ms,
        generation_route=resolved_generation_route,
        planner_items=planner_items,
        planned_items_block=planned_block,
        cluster_planner_runs=cluster_planner_runs,
        combined_cluster_plans_block=combined_cluster_plans_block,
        renderer_raw_response=renderer_raw_response,
        renderer_skipped=renderer_skipped,
        prompt_files=prompt_files,
    )


def _run_sections_sequential(
    jobs: list[SectionGenerationJob],
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    linked_evidence_two_step: bool,
    generation_route: str | None = None,
    cluster_planner_concurrency: int | None = None,
) -> list[SectionGenerationRun]:
    return [
        _run_section_generation_job(
            job,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
            generation_route=generation_route,
            cluster_planner_concurrency=cluster_planner_concurrency,
        )
        for job in jobs
    ]


def _run_sections_parallel(
    jobs: list[SectionGenerationJob],
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    linked_evidence_two_step: bool,
    section_concurrency: int,
    generation_route: str | None = None,
    cluster_planner_concurrency: int | None = None,
) -> list[SectionGenerationRun]:
    max_workers = (
        len(jobs) if section_concurrency == 0 else min(len(jobs), section_concurrency)
    )
    runs_by_section: dict[str, SectionGenerationRun] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_section_generation_job,
                job,
                template=template,
                model_spec=model_spec,
                system_prompt=system_prompt,
                prompt_version=prompt_version,
                linked_evidence_two_step=linked_evidence_two_step,
                generation_route=generation_route,
                cluster_planner_concurrency=cluster_planner_concurrency,
            ): job.section_id
            for job in jobs
        }
        for future in as_completed(futures):
            section_run = future.result()
            runs_by_section[section_run.section_id] = section_run
    section_order = [job.section_id for job in jobs]
    return [runs_by_section[section_id] for section_id in section_order]


def run_generation_session(
    *,
    session_id: str,
    assignments: list[ClusterAssignmentInput],
    clusters: list[ClusterCase],
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    section_concurrency: int | None = None,
    section_context: SectionContext | None = None,
    section_evidence: SectionEvidence | None = None,
    transcript_directives: list[Directive] | None = None,
    prompt_version: str = "v003",
    linked_evidence_two_step: bool = False,
    generation_route: str | None = None,
    cluster_planner_concurrency: int | None = None,
) -> GenerationSessionRun:
    if not clusters and not section_context:
        raise ValueError(
            "generation_session_requires_clusters_or_section_context"
        )

    resolved_concurrency = resolve_section_concurrency(section_concurrency)
    clusters_by_id = {cluster.id: cluster for cluster in clusters}
    section_plan = plan_section_generation(
        assignments,
        clusters_by_id,
        template,
        section_context=section_context,
        section_evidence=section_evidence,
        transcript_directives=transcript_directives,
    )

    if not section_plan.jobs:
        raise ValueError("generation_session_has_no_sections_to_generate")

    use_parallel = len(section_plan.jobs) > 1 and resolved_concurrency != 1
    section_execution_mode = "parallel" if use_parallel else "sequential"

    started_at = time.perf_counter()
    if use_parallel:
        section_runs = _run_sections_parallel(
            section_plan.jobs,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
            generation_route=generation_route,
            section_concurrency=resolved_concurrency,
            cluster_planner_concurrency=cluster_planner_concurrency,
        )
    else:
        section_runs = _run_sections_sequential(
            section_plan.jobs,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
            generation_route=generation_route,
            cluster_planner_concurrency=cluster_planner_concurrency,
        )
    total_response_time_ms = int((time.perf_counter() - started_at) * 1000)

    llm_responses = [
        response
        for section_run in section_runs
        for response in section_run.llm_responses
    ]
    sum_section_response_time_ms = sum(
        section_run.response_time_ms for section_run in section_runs
    )
    session_result = GenerationSessionResult(
        sections=[section_run.result for section_run in section_runs],
        skipped_sections=section_plan.skipped_sections,
    )
    llm_usage_summary = summarize_llm_responses(llm_responses)
    llm_usage_summary = {
        **llm_usage_summary,
        "section_execution_mode": section_execution_mode,
        "section_concurrency": resolved_concurrency,
        "sum_section_response_time_ms": sum_section_response_time_ms,
    }
    return GenerationSessionRun(
        session_id=session_id,
        section_plan=section_plan,
        section_runs=section_runs,
        session_result=session_result,
        total_response_time_ms=total_response_time_ms,
        sum_section_response_time_ms=sum_section_response_time_ms,
        section_execution_mode=section_execution_mode,
        section_concurrency=resolved_concurrency,
        llm_usage_summary=llm_usage_summary,
    )
