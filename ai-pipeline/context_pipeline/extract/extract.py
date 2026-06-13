from __future__ import annotations

from pathlib import Path

from common.context_claims import ClinicalClaim, ExtractResult
from common.providers import ModelSpec, call_llm
from context_pipeline.extract.lib import (
    DocumentFixture,
    DocumentTextChunk,
    ExtractChunkInput,
    merge_extract_results,
    normalize_extract_claims,
    parse_extract_result,
    render_extract_user_payload,
)


def run_extract_document(
    *,
    fixture: DocumentFixture,
    chunks: list[DocumentTextChunk],
    model_spec: ModelSpec,
    system_prompt: str,
) -> tuple[ExtractResult, list[str]]:
    chunk_results: list[ExtractResult] = []
    chunk_claims: list[list[ClinicalClaim]] = []
    raw_responses: list[str] = []

    for chunk in chunks:
        chunk_input = ExtractChunkInput(
            session_id=fixture.session_id,
            document_id=fixture.document_id,
            document_kind=fixture.document_kind,
            chunk_index=chunk.chunk_index,
            chunk_count=chunk.chunk_count,
            document_text=chunk.text,
        )
        raw_response = call_llm(
            provider=model_spec.provider,
            model=model_spec.model,
            system=system_prompt,
            user=render_extract_user_payload(chunk_input),
        )
        parsed = parse_extract_result(raw_response)
        if parsed.document_id != fixture.document_id:
            raise ValueError(
                "extract_document_id_mismatch: "
                f"expected {fixture.document_id!r}, got {parsed.document_id!r}"
            )
        claims = normalize_extract_claims(
            parsed,
            session_id=fixture.session_id,
            chunk_index=chunk.chunk_index,
        )
        chunk_results.append(parsed)
        chunk_claims.append(claims)
        raw_responses.append(raw_response)

    merged = merge_extract_results(chunk_results, chunk_claims)
    return merged, raw_responses


def run_extract_fixture(
    *,
    fixture: DocumentFixture,
    cases_dir: Path,
    model_spec: ModelSpec,
    system_prompt: str,
    token_budget: int,
) -> tuple[ExtractResult, list[str]]:
    from context_pipeline.extract.lib import load_document_text

    chunks = load_document_text(
        fixture,
        cases_dir=cases_dir,
        token_budget=token_budget,
    )
    return run_extract_document(
        fixture=fixture,
        chunks=chunks,
        model_spec=model_spec,
        system_prompt=system_prompt,
    )
