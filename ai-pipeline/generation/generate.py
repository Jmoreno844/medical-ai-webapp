from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from classification.lib import ClusterCase
from common.context_claims import ClaimAssignment, ClinicalClaim
from common.llm_response import LlmResponse, summarize_llm_responses
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate
from generation.lib import (
    DEFAULT_SECTION_CONCURRENCY,
    ClusterAssignmentInput,
    GenerationSessionResult,
    SectionGenerationJob,
    SectionGenerationPlan,
    SectionGenerationResult,
    parse_section_generation_result,
    plan_section_generation,
    render_section_user_payload,
)


@dataclass(frozen=True, slots=True)
class SectionGenerationRun:
    section_id: str
    cluster_ids: list[str]
    claim_ids: list[str]
    result: SectionGenerationResult
    llm_response: LlmResponse
    raw_response: str
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
) -> tuple[SectionGenerationResult, LlmResponse, int]:
    user_payload = render_section_user_payload(
        section=job.section,
        clusters=job.clusters,
        enrichment_claims=job.enrichment_claims,
        template=template,
    )
    started_at = time.perf_counter()
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = parse_section_generation_result(
        llm_response.content,
        expected_section_id=job.section_id,
    )
    return result, llm_response, response_time_ms


def _run_section_generation_job(
    job: SectionGenerationJob,
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
) -> SectionGenerationRun:
    result, llm_response, response_time_ms = run_section_generation(
        job=job,
        template=template,
        model_spec=model_spec,
        system_prompt=system_prompt,
    )
    return SectionGenerationRun(
        section_id=job.section_id,
        cluster_ids=job.cluster_ids,
        claim_ids=job.claim_ids,
        result=result,
        llm_response=llm_response,
        raw_response=llm_response.content,
        response_time_ms=response_time_ms,
    )


def _run_sections_sequential(
    jobs: list[SectionGenerationJob],
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
) -> list[SectionGenerationRun]:
    return [
        _run_section_generation_job(
            job,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
        for job in jobs
    ]


def _run_sections_parallel(
    jobs: list[SectionGenerationJob],
    *,
    template: ClinicalTemplate,
    model_spec: ModelSpec,
    system_prompt: str,
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
    claim_assignments: list[ClaimAssignment] | None = None,
    claims_by_id: dict[str, ClinicalClaim] | None = None,
) -> GenerationSessionRun:
    if not clusters and not (claim_assignments and claims_by_id):
        raise ValueError(
            "generation_session_requires_clusters_or_claim_assignments"
        )

    resolved_concurrency = resolve_section_concurrency(section_concurrency)
    clusters_by_id = {cluster.id: cluster for cluster in clusters}
    section_plan = plan_section_generation(
        assignments,
        clusters_by_id,
        template,
        claim_assignments=claim_assignments,
        claims_by_id=claims_by_id,
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
            section_concurrency=resolved_concurrency,
        )
    else:
        section_runs = _run_sections_sequential(
            section_plan.jobs,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
    total_response_time_ms = int((time.perf_counter() - started_at) * 1000)

    llm_responses = [section_run.llm_response for section_run in section_runs]
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
