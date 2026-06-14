from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from common.context_spans import (
    Directive,
    SectionAdapterResult,
    Span,
    SpanCluster,
    audit_section_adapter_result,
    span_to_payload_item,
)
from common.json_utils import extract_json_object
from common.llm_response import LlmResponse, summarize_llm_responses
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path
from common.providers import ModelSpec, call_llm_detailed
from common.templates import ClinicalTemplate, TemplateSection

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "section_adapter"
DEFAULT_SECTION_CONCURRENCY = 0


@dataclass(frozen=True, slots=True)
class SectionAdapterRun:
    section_id: str
    cluster_ids: list[str]
    result: SectionAdapterResult
    llm_response: LlmResponse
    response_time_ms: int


@dataclass(frozen=True, slots=True)
class SectionAdapterSessionRun:
    section_runs: list[SectionAdapterRun]
    section_context: dict[str, str]
    total_response_time_ms: int
    section_execution_mode: str
    section_concurrency: int
    llm_usage_summary: dict[str, object]


def section_adapter_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_section_adapter_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return section_adapter_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_section_adapter_prompt(version)


def resolve_section_concurrency(raw: int | None = None) -> int:
    if raw is not None:
        return max(0, raw)
    env_value = os.environ.get(
        "CONTEXT_SECTION_ADAPTER_CONCURRENCY",
        str(DEFAULT_SECTION_CONCURRENCY),
    ).strip()
    if not env_value:
        return DEFAULT_SECTION_CONCURRENCY
    return max(0, int(env_value))


def render_section_adapter_payload(
    *,
    section: TemplateSection,
    encounter_date: str | None,
    directives: list[Directive],
    clusters: list[SpanCluster],
    spans: list[Span],
) -> str:
    payload = {
        "section_id": section.section_id,
        "section_description": section.description,
        "encounter_date": encounter_date,
        "directives": [directive.model_dump(mode="json") for directive in directives],
        "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
        "spans": [span_to_payload_item(span) for span in spans],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_section_adapter_result(
    raw: str,
    *,
    expected_section_id: str,
) -> SectionAdapterResult:
    payload = extract_json_object(raw)
    try:
        result = SectionAdapterResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"section_adapter_invalid_result: {exc}") from exc
    audit_section_adapter_result(expected_section_id, result)
    return result


def enrich_section_adapter_session_for_export(
    section_context: dict[str, str],
) -> dict[str, object]:
    sections = [
        {
            "section_id": section_id,
            "content": content,
            "content_chars": len(content),
        }
        for section_id, content in sorted(section_context.items())
        if content.strip()
    ]
    return {
        "section_context": dict(section_context),
        "sections": sections,
        "section_count": len(sections),
    }


def _run_section_adapter_job(
    *,
    section: TemplateSection,
    cluster_ids: list[str],
    clusters_by_id: dict[str, SpanCluster],
    spans_by_id: dict[str, Span],
    encounter_date: str | None,
    directives: list[Directive],
    model_spec: ModelSpec,
    system_prompt: str,
) -> SectionAdapterRun:
    clusters = [clusters_by_id[cluster_id] for cluster_id in cluster_ids]
    span_ids: list[str] = []
    for cluster in clusters:
        for span_id in cluster.span_ids:
            if span_id not in span_ids:
                span_ids.append(span_id)
    spans = [spans_by_id[span_id] for span_id in span_ids]
    user_payload = render_section_adapter_payload(
        section=section,
        encounter_date=encounter_date,
        directives=directives,
        clusters=clusters,
        spans=spans,
    )
    started_at = time.perf_counter()
    llm_response = call_llm_detailed(
        provider=model_spec.provider,
        model=model_spec.model,
        system=system_prompt,
        user=user_payload,
    )
    response_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = parse_section_adapter_result(
        llm_response.content,
        expected_section_id=section.section_id,
    )
    return SectionAdapterRun(
        section_id=section.section_id,
        cluster_ids=cluster_ids,
        result=result,
        llm_response=llm_response,
        response_time_ms=response_time_ms,
    )


def run_section_adapter_session(
    *,
    adapter_jobs: dict[str, list[str]],
    clusters: list[SpanCluster],
    spans: list[Span],
    template: ClinicalTemplate,
    encounter_date: str | None,
    directives: list[Directive],
    model_spec: ModelSpec,
    system_prompt: str,
    section_concurrency: int | None = None,
) -> SectionAdapterSessionRun:
    if not adapter_jobs:
        return SectionAdapterSessionRun(
            section_runs=[],
            section_context={},
            total_response_time_ms=0,
            section_execution_mode="sequential",
            section_concurrency=0,
            llm_usage_summary={},
        )

    resolved_concurrency = resolve_section_concurrency(section_concurrency)
    clusters_by_id = {cluster.id: cluster for cluster in clusters}
    spans_by_id = {span.id: span for span in spans}
    sections_by_id = {section.section_id: section for section in template.sections}
    jobs = [
        (section_id, cluster_ids)
        for section_id, cluster_ids in adapter_jobs.items()
        if cluster_ids
    ]

    use_parallel = len(jobs) > 1 and resolved_concurrency != 1
    section_execution_mode = "parallel" if use_parallel else "sequential"
    started_at = time.perf_counter()

    def run_job(job: tuple[str, list[str]]) -> SectionAdapterRun:
        section_id, cluster_ids = job
        return _run_section_adapter_job(
            section=sections_by_id[section_id],
            cluster_ids=cluster_ids,
            clusters_by_id=clusters_by_id,
            spans_by_id=spans_by_id,
            encounter_date=encounter_date,
            directives=directives,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )

    section_runs: list[SectionAdapterRun]
    if use_parallel:
        max_workers = (
            len(jobs) if resolved_concurrency == 0 else min(len(jobs), resolved_concurrency)
        )
        runs_by_section: dict[str, SectionAdapterRun] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_job, job): job[0]
                for job in jobs
            }
            for future in as_completed(futures):
                section_run = future.result()
                runs_by_section[section_run.section_id] = section_run
        section_runs = [runs_by_section[section_id] for section_id, _ in jobs]
    else:
        section_runs = [run_job(job) for job in jobs]

    total_response_time_ms = int((time.perf_counter() - started_at) * 1000)
    section_context = {
        section_run.section_id: section_run.result.content.strip()
        for section_run in section_runs
        if section_run.result.content.strip()
    }
    llm_usage_summary = summarize_llm_responses(
        [section_run.llm_response for section_run in section_runs]
    )
    llm_usage_summary = {
        **llm_usage_summary,
        "section_execution_mode": section_execution_mode,
        "section_concurrency": resolved_concurrency,
    }
    return SectionAdapterSessionRun(
        section_runs=section_runs,
        section_context=section_context,
        total_response_time_ms=total_response_time_ms,
        section_execution_mode=section_execution_mode,
        section_concurrency=resolved_concurrency,
        llm_usage_summary=llm_usage_summary,
    )


__all__ = [
    "DEFAULT_SECTION_CONCURRENCY",
    "MODULE_ROOT",
    "SectionAdapterRun",
    "SectionAdapterSessionRun",
    "enrich_section_adapter_session_for_export",
    "load_prompt",
    "load_section_adapter_prompt",
    "parse_section_adapter_result",
    "prompt_file_path",
    "render_section_adapter_payload",
    "resolve_section_concurrency",
    "run_section_adapter_session",
]
