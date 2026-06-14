from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.context_claims import ClinicalClaim, merge_claim_lists
from common.llm_response import LlmResponse
from common.providers import ModelSpec
from common.templates import load_template
from context_pipeline.classify_claims.classify_claims import run_classify_claims_session
from context_pipeline.classify_claims.lib import ClaimClassificationSessionResult
from context_pipeline.decompose.decompose import run_decompose
from context_pipeline.decompose.lib import (
    load_context_case,
    load_context_cases,
    select_context_case,
)
from context_pipeline.extract.extract import run_extract_fixture
from context_pipeline.extract.lib import load_document_fixture


@dataclass(frozen=True, slots=True)
class ContextLlmCall:
    label: str
    provider: str
    model: str
    llm_response: LlmResponse


@dataclass(frozen=True, slots=True)
class ContextPipelineRun:
    session_id: str
    template_id: str
    doctor_claims: list[ClinicalClaim]
    document_claims: list[ClinicalClaim]
    all_claims: list[ClinicalClaim]
    classification_result: ClaimClassificationSessionResult
    llm_calls: list[ContextLlmCall]


def run_context_pipeline_session(
    *,
    case_id: str,
    cases_index: Path,
    templates_dir: Path,
    model_spec: ModelSpec,
    decompose_prompt: str,
    extract_prompt: str,
    classify_prompt: str,
    token_budget: int,
) -> ContextPipelineRun:
    case_meta = select_context_case(load_context_cases(cases_index), case_id=case_id)
    context_case = load_context_case(case_meta, cases_dir=cases_index.parent)
    template = load_template(case_meta.template_id, templates_dir=templates_dir)
    llm_calls: list[ContextLlmCall] = []

    doctor_claims, decompose_response = run_decompose(
        case=context_case.doctor_note,
        model_spec=model_spec,
        system_prompt=decompose_prompt,
    )
    llm_calls.append(
        ContextLlmCall(
            label="decompose",
            provider=model_spec.provider,
            model=model_spec.model,
            llm_response=decompose_response,
        )
    )

    document_claim_lists: list[list[ClinicalClaim]] = []
    for document_file in case_meta.document_files:
        fixture = load_document_fixture(cases_index.parent / document_file)
        extract_result, extract_responses = run_extract_fixture(
            fixture=fixture,
            cases_dir=cases_index.parent,
            model_spec=model_spec,
            system_prompt=extract_prompt,
            token_budget=token_budget,
        )
        document_claim_lists.append(extract_result.claims)
        for chunk_index, extract_response in enumerate(extract_responses, start=1):
            llm_calls.append(
                ContextLlmCall(
                    label=f"extract:{fixture.document_id}:chunk{chunk_index}",
                    provider=model_spec.provider,
                    model=model_spec.model,
                    llm_response=extract_response,
                )
            )

    document_claims = (
        merge_claim_lists(*document_claim_lists) if document_claim_lists else []
    )
    all_claims = (
        merge_claim_lists(doctor_claims, document_claims)
        if document_claims
        else doctor_claims
    )

    classification_result, classify_response = run_classify_claims_session(
        claims=all_claims,
        template=template,
        model_spec=model_spec,
        system_prompt=classify_prompt,
    )
    llm_calls.append(
        ContextLlmCall(
            label="classify_claims",
            provider=model_spec.provider,
            model=model_spec.model,
            llm_response=classify_response,
        )
    )

    return ContextPipelineRun(
        session_id=case_meta.session_id,
        template_id=case_meta.template_id,
        doctor_claims=doctor_claims,
        document_claims=document_claims,
        all_claims=all_claims,
        classification_result=classification_result,
        llm_calls=llm_calls,
    )
