"""R&D session runner over local context fixtures."""

from __future__ import annotations

from pathlib import Path

from document_pipeline_core.common.context_spans import TriageResult, split_doctor_items
from document_pipeline_core.common.providers import ModelSpec
from document_pipeline_core.common.templates import load_template
from document_pipeline_core.context_pipeline.config import ContextPipelinePromptBundle
from document_pipeline_core.context_pipeline.session import (
    ContextLlmCall,
    ContextPipelinePartialError,
    ContextPipelineRun,
    run_context_pipeline_ad_hoc,
    run_context_pipeline_core,
)
from document_pipeline_core.context_pipeline.span_pool import build_context_span_pools_from_case
from document_pipeline_core.context_pipeline.triage.triage import run_triage

from harness.context_cases import (
    load_context_case,
    load_context_cases,
    select_context_case,
)


def _primary_document_date(context_case) -> str | None:
    for fixture in context_case.document_fixtures:
        if fixture.document_date:
            return fixture.document_date
    return None


def run_context_pipeline_session(
    *,
    case_id: str,
    cases_index: Path,
    templates_dir: Path,
    model_spec: ModelSpec,
    prompt_bundle: ContextPipelinePromptBundle,
    include_doctor_note: bool = True,
    include_documents: bool = True,
    template_id_override: str | None = None,
) -> ContextPipelineRun:
    case_meta = select_context_case(load_context_cases(cases_index), case_id=case_id)
    context_case = load_context_case(case_meta, cases_dir=cases_index.parent)
    resolved_template_id = template_id_override or case_meta.template_id
    template = load_template(resolved_template_id, templates_dir=templates_dir)
    llm_calls: list[ContextLlmCall] = []
    available_documents = (
        [fixture.document_id for fixture in context_case.document_fixtures]
        if include_documents
        else []
    )
    template_section_ids = [section.section_id for section in template.sections]

    doctor_items, is_pasted = split_doctor_items(
        context_case.doctor_note.doctor_note,
        session_id=case_meta.session_id,
    )
    if include_doctor_note and not doctor_items:
        raise ValueError("context_pipeline_requires_doctor_note_items")

    triage_result = TriageResult()
    if include_doctor_note:
        triage_result, triage_response = run_triage(
            session_id=case_meta.session_id,
            items=doctor_items,
            model_spec=model_spec,
            system_prompt=prompt_bundle.triage.system_prompt,
            prompt_version=prompt_bundle.triage.prompt_version,
            available_documents=available_documents,
            template_section_ids=template_section_ids,
        )
        llm_calls.append(
            ContextLlmCall(
                label="triage",
                provider=model_spec.provider,
                model=model_spec.model,
                llm_response=triage_response,
            )
        )

    span_pools = build_context_span_pools_from_case(
        context_case=context_case,
        cases_dir=cases_index.parent,
        doctor_items=doctor_items,
        triage_result=triage_result,
        is_pasted=is_pasted,
        include_doctor_note=include_doctor_note,
        include_documents=include_documents,
    )

    return run_context_pipeline_core(
        session_id=case_meta.session_id,
        template=template,
        template_id=resolved_template_id,
        encounter_date=case_meta.encounter_date,
        document_date=_primary_document_date(context_case),
        doctor_items=doctor_items,
        is_pasted=is_pasted,
        triage_result=triage_result,
        span_pools=span_pools,
        model_spec=model_spec,
        prompt_bundle=prompt_bundle,
        llm_calls=llm_calls,
    )


__all__ = [
    "ContextLlmCall",
    "ContextPipelinePartialError",
    "ContextPipelineRun",
    "run_context_pipeline_ad_hoc",
    "run_context_pipeline_session",
]
