from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from common.context_claims import (
    ClaimSourceType,
    ClinicalClaim,
    ExtractResult,
)
from common.json_utils import extract_json_object
from common.prompts import (
    load_prompt as load_prompt_from_file,
)
from common.prompts import (
    prompt_file_path as resolve_prompt_file_path,
)
from context_pipeline.extract.pdf_text import chunk_text_by_tokens, pdf_to_text

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = Path(__file__).resolve().parent
CONTEXT_CASES_DIR = AI_PIPELINE_ROOT / "context_pipeline" / "cases"
DEFAULT_CASES_INDEX = CONTEXT_CASES_DIR / "index.json"
DEFAULT_EXTRACT_TOKEN_BUDGET = 3000
DEFAULT_TOKEN_ENCODING = "cl100k_base"
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "extract"


class DocumentFixture(BaseModel):
    session_id: str
    document_id: str
    document_kind: str | None = None
    source_file: str


class ExtractChunkInput(BaseModel):
    session_id: str
    document_id: str
    document_kind: str | None = None
    chunk_index: int
    chunk_count: int
    document_text: str


@dataclass(frozen=True, slots=True)
class DocumentTextChunk:
    chunk_index: int
    chunk_count: int
    text: str


def extract_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_extract_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return extract_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_extract_prompt(version)


def load_document_fixture(path: Path) -> DocumentFixture:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return DocumentFixture.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"context_document_fixture_invalid: {exc}") from exc


def resolve_document_pdf_path(
    fixture: DocumentFixture,
    *,
    cases_dir: Path,
) -> Path:
    return (cases_dir / fixture.source_file).resolve()


def load_document_text(
    fixture: DocumentFixture,
    *,
    cases_dir: Path,
    token_budget: int = DEFAULT_EXTRACT_TOKEN_BUDGET,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
) -> list[DocumentTextChunk]:
    pdf_path = resolve_document_pdf_path(fixture, cases_dir=cases_dir)
    full_text = pdf_to_text(pdf_path)
    if not full_text.strip():
        raise ValueError(f"extract_pdf_empty_text: {pdf_path}")
    chunk_texts = chunk_text_by_tokens(
        full_text,
        max_tokens=token_budget,
        encoding_name=encoding_name,
    )
    chunk_count = len(chunk_texts)
    return [
        DocumentTextChunk(
            chunk_index=index,
            chunk_count=chunk_count,
            text=text,
        )
        for index, text in enumerate(chunk_texts)
    ]


def render_extract_user_payload(chunk_input: ExtractChunkInput) -> str:
    return json.dumps(chunk_input.model_dump(), ensure_ascii=False, indent=2)


def parse_extract_result(raw: str) -> ExtractResult:
    payload = extract_json_object(raw)
    try:
        return ExtractResult.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"extract_invalid_result: {exc}") from exc


def normalize_extract_claims(
    result: ExtractResult,
    *,
    session_id: str,
    chunk_index: int | None = None,
) -> list[ClinicalClaim]:
    claims: list[ClinicalClaim] = []
    seen_ids: set[str] = set()
    for index, claim in enumerate(result.claims):
        claim_id = claim.claim_id.strip()
        if not claim_id:
            suffix = f"{chunk_index}_{index}" if chunk_index is not None else str(index)
            claim_id = f"{session_id}_{result.document_id}_{suffix}"
        if claim_id in seen_ids:
            raise ValueError(f"extract_duplicate_claim_id: {claim_id!r}")
        seen_ids.add(claim_id)
        source_ref = claim.source_ref
        if source_ref is None and chunk_index is not None:
            from common.context_claims import ClaimSourceRef

            source_ref = ClaimSourceRef(
                document_id=result.document_id,
                chunk_index=chunk_index,
            )
        elif source_ref is not None and source_ref.document_id is None:
            source_ref = source_ref.model_copy(
                update={"document_id": result.document_id}
            )
        claims.append(
            ClinicalClaim(
                claim_id=claim_id,
                text=claim.text.strip(),
                source_type=ClaimSourceType.PATIENT_DOCUMENT,
                claim_type=claim.claim_type,
                source_ref=source_ref,
                event_date=claim.event_date,
                document_kind=result.document_kind,
            )
        )
    return claims


def merge_extract_results(
    chunk_results: list[ExtractResult],
    chunk_claims: list[list[ClinicalClaim]],
) -> ExtractResult:
    if not chunk_results:
        raise ValueError("extract_merge_requires_at_least_one_chunk")
    document_id = chunk_results[0].document_id
    document_kind = chunk_results[0].document_kind
    summaries = [
        result.document_summary.strip()
        for result in chunk_results
        if result.document_summary.strip()
    ]
    document_summary = summaries[0] if summaries else ""
    merged_claims: list[ClinicalClaim] = []
    seen_ids: set[str] = set()
    for claims in chunk_claims:
        for claim in claims:
            if claim.claim_id in seen_ids:
                raise ValueError(f"extract_duplicate_claim_id: {claim.claim_id!r}")
            seen_ids.add(claim.claim_id)
            merged_claims.append(claim)
    return ExtractResult(
        document_id=document_id,
        document_kind=document_kind,
        document_summary=document_summary,
        claims=merged_claims,
    )


def enrich_extract_result_for_export(result: ExtractResult) -> dict[str, object]:
    return {
        "document_id": result.document_id,
        "document_kind": result.document_kind,
        "document_summary": result.document_summary,
        "claims": [claim.model_dump(mode="json") for claim in result.claims],
        "claim_count": len(result.claims),
    }


def format_extract_debug_output(result: ExtractResult) -> str:
    lines = [
        f"document_id: {result.document_id}",
        f"document_kind: {result.document_kind}",
        f"document_summary: {result.document_summary or '(none)'}",
        "claims:",
    ]
    if not result.claims:
        lines.append("  (none)")
    else:
        for claim in result.claims:
            preview = claim.text
            if len(preview) > 100:
                preview = preview[:97] + "..."
            lines.append(
                f"  - {claim.claim_id} ({claim.claim_type.value}): {preview}"
            )
    lines.append(f"\nsummary: claim_count={len(result.claims)}")
    return "\n".join(lines)
