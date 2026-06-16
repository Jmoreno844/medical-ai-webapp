from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from classification.lib import ClusterCase
from common.context_spans import Directive, SectionContext, SectionEvidence
from common.llm_response import LlmResponse, summarize_llm_responses
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate
from generation.evidence_markers import audit_evidence_markers
from generation.lib import (
    DEFAULT_SECTION_CONCURRENCY,
    ClusterAssignmentInput,
    GenerationSessionResult,
    GenerationValidationError,
    SectionGenerationJob,
    SectionGenerationPlan,
    SectionGenerationResult,
    collect_allowed_evidence_id_set,
    generation_direct_output_schema,
    generation_direct_uses_py_prompt,
    generation_planner_output_schema,
    load_generation_planner_prompt,
    load_generation_renderer_prompt,
    normalize_section_generation_content,
    parse_linked_content,
    parse_planner_items_result,
    parse_section_generation_result,
    plan_section_generation,
    planner_items_to_export,
    render_direct_payload,
    render_planned_items_block,
    render_planner_payload,
    render_renderer_payload,
    render_section_user_payload,
    should_use_two_step_generation,
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
) -> None:
    if isinstance(exc, GenerationValidationError):
        raise exc
    kwargs = _job_diagnostics_kwargs(
        job,
        generation_route=generation_route,
        generation_substep=generation_substep,
        prompt_version=prompt_version,
    )
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


def run_section_generation(
    *,
    job: SectionGenerationJob,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str = "v003",
    linked_evidence_two_step: bool = False,
) -> tuple[
    SectionGenerationResult,
    list[LlmResponse],
    int,
    str,
    list[dict[str, object]] | None,
    str | None,
]:
    if generation_direct_uses_py_prompt(prompt_version):
        if should_use_two_step_generation(
            job,
            linked_evidence_two_step=linked_evidence_two_step,
        ):
            return run_two_step_section_generation(
                job=job,
                template=template,
                model_spec=model_spec,
                prompt_version=prompt_version,
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
        return result, [llm_response], response_time_ms, "direct", None, None

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
    return result, [llm_response], response_time_ms, "legacy", None, None


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
        "two_step",
        exported_items,
        planned_block,
    )


def _run_section_generation_job(
    job: SectionGenerationJob,
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    linked_evidence_two_step: bool,
) -> SectionGenerationRun:
    (
        result,
        llm_responses,
        response_time_ms,
        generation_route,
        planner_items,
        planned_block,
    ) = (
        run_section_generation(
            job=job,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
        )
    )
    return SectionGenerationRun(
        section_id=job.section_id,
        cluster_ids=job.cluster_ids,
        context_present=job.context_present,
        context_chars=job.context_chars,
        result=result,
        llm_responses=llm_responses,
        raw_response=llm_responses[-1].content,
        response_time_ms=response_time_ms,
        generation_route=generation_route,
        planner_items=planner_items,
        planned_items_block=planned_block,
    )


def _run_sections_sequential(
    jobs: list[SectionGenerationJob],
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
    prompt_version: str,
    linked_evidence_two_step: bool,
) -> list[SectionGenerationRun]:
    return [
        _run_section_generation_job(
            job,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
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
            section_concurrency=resolved_concurrency,
        )
    else:
        section_runs = _run_sections_sequential(
            section_plan.jobs,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            linked_evidence_two_step=linked_evidence_two_step,
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
