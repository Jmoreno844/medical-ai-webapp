from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CopilotPatch, Document, Encounter
from app.db.session import get_db_session
from app.domains.copilot.document_sections import extract_document_sections
from app.domains.copilot.internal_jwt import require_copilot_tools_jwt
from app.domains.copilot.schemas import (
    CopilotEncounterContextOut,
    CopilotListEncounterDocumentsIn,
    CopilotListEncounterDocumentsOut,
    CopilotListOpenDocumentsIn,
    CopilotListOpenDocumentsOut,
    CopilotReadDocumentIn,
    CopilotReadDocumentOut,
    CopilotReadDocumentSpanIn,
    CopilotReadDocumentSpanOut,
    CopilotReadDocumentSummaryIn,
    CopilotReadDocumentSummaryOut,
    CopilotReadEncounterContextIn,
    CopilotReadPatchHistoryIn,
    CopilotReadPatchHistoryOut,
    CopilotSearchDocumentMatchOut,
    CopilotSearchDocumentsIn,
    CopilotSearchDocumentsOut,
    CopilotToolDocumentOut,
)

router = APIRouter(prefix="/internal/copilot/tools", tags=["copilot-internal-tools"])

DOCUMENT_TITLES = {
    "context": "Contexto del encuentro",
    "transcription": "Transcripcion",
    "template": "Plantilla",
    "note": "Nota clinica",
}


def _document_ai_writable(document_kind: str) -> bool:
    # Internal encounter listings must mirror the copilot write contract:
    # transcriptions are read-only, while clinician-facing editable docs stay writable.
    return document_kind != "transcription"


def _validate_tool_request(
    *,
    claims: dict[str, Any],
    run_id: str,
    thread_id: str,
    encounter_id: int,
    user_id: int,
) -> None:
    expected = {
        "run_id": run_id,
        "thread_id": thread_id,
        "encounter_id": str(encounter_id),
        "user_id": str(user_id),
    }
    for claim_name, expected_value in expected.items():
        if str(claims.get(claim_name)) != expected_value:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Claim interno invalido para {claim_name}")


async def _get_owned_encounter(
    session: AsyncSession, *, encounter_id: int, user_id: int
) -> Encounter:
    result = await session.execute(
        select(Encounter).options(selectinload(Encounter.patient)).where(Encounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()
    if encounter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    if encounter.doctor_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para acceder a este encuentro")
    return encounter


async def _get_owned_document(
    session: AsyncSession, *, document_id: int, encounter_id: int, user_id: int
) -> Document:
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.doctor_template))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    if document.encounter_id != encounter_id or document.doctor_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para acceder a este documento")
    return document


async def _get_encounter_documents(
    session: AsyncSession, *, encounter_id: int, user_id: int
) -> list[Document]:
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.doctor_template))
        .where(Document.encounter_id == encounter_id, Document.doctor_id == user_id)
        .order_by(Document.created_on, Document.id)
    )
    return list(result.scalars().all())


def _document_sections_payload(document: Document) -> dict[str, Any]:
    return extract_document_sections(
        content_markdown=document.content_markdown,
        content_json=document.content_json,
    )


def _document_title(kind: str, document_id: int, *, template_name: str | None = None) -> str:
    if template_name and kind in ("note", "template"):
        return template_name
    return DOCUMENT_TITLES.get(kind, f"Documento {document_id}")


def _build_excerpt(content: str, *, query: str | None = None, max_length: int = 240) -> str:
    if not content.strip():
        return ""
    normalized_content = " ".join(content.split())
    if query:
        lower_content = normalized_content.lower()
        lower_query = query.lower()
        index = lower_content.find(lower_query)
        if index >= 0:
            start = max(index - 80, 0)
            end = min(index + len(query) + 120, len(normalized_content))
            return normalized_content[start:end].strip()
    return normalized_content[:max_length].strip()


def _document_version(_document: Document) -> int:
    return 1


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _anchor_for_span(content: str, start: int, end: int) -> dict[str, Any]:
    return {
        "exactText": content[start:end],
        "prefixText": content[max(0, start - 48) : start],
        "suffixText": content[end : min(len(content), end + 48)],
        "startOffset": start,
        "endOffset": end,
    }


def _find_anchor_span(
    *,
    content: str,
    exact_text: str | None = None,
    prefix_text: str | None = None,
    suffix_text: str | None = None,
    start_offset: int | None = None,
    end_offset: int | None = None,
) -> tuple[int, int]:
    if start_offset is not None and end_offset is not None and 0 <= start_offset <= end_offset <= len(content):
        return start_offset, end_offset
    if exact_text:
        matches: list[int] = []
        cursor = 0
        while True:
            index = content.find(exact_text, cursor)
            if index == -1:
                break
            matches.append(index)
            cursor = index + 1
        if not matches:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontro el span solicitado en el documento")
        if len(matches) == 1:
            start = matches[0]
            return start, start + len(exact_text)
        narrowed = []
        for index in matches:
            prefix_match = prefix_text is None or content[max(0, index - len(prefix_text)) : index] == prefix_text
            suffix_start = index + len(exact_text)
            suffix_match = suffix_text is None or content[suffix_start : suffix_start + len(suffix_text)] == suffix_text
            if prefix_match and suffix_match:
                narrowed.append(index)
        if len(narrowed) != 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "El anchor es ambiguo o no coincide de forma unica con el documento actual",
            )
        start = narrowed[0]
        return start, start + len(exact_text)
    # prefix_text-only path: the LLM knows where a section STARTS (e.g. a markdown
    # header like "## 10. Plan de manejo") but cannot know where it ends without
    # reading it first. We treat prefix_text as a section-start anchor and return
    # from that position to the next markdown header (#/##) or end of document.
    # Without this path the backend silently fell back to returning the first 400
    # chars of the document, which is wrong and confusing.
    if prefix_text:
        matches: list[int] = []
        cursor = 0
        normalized_prefix = " ".join(prefix_text.split())
        while True:
            # Search with whitespace normalization to tolerate minor spacing diffs.
            index = content.find(prefix_text, cursor)
            if index == -1:
                # Also try a normalized single-space variant in case the document
                # uses a different whitespace sequence (e.g. Windows line endings).
                normalized_content = " ".join(content.split())
                norm_index = normalized_content.find(normalized_prefix)
                if norm_index != -1 and not matches:
                    # Best-effort: map the normalized index back to raw content by
                    # using the same phrase on the raw content with find().
                    raw_index = content.find(prefix_text.strip())
                    if raw_index != -1:
                        matches.append(raw_index)
                break
            matches.append(index)
            cursor = index + 1

        if not matches:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontro el prefix_text solicitado en el documento")
        if len(matches) > 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "El prefix_text es ambiguo: aparece mas de una vez en el documento")

        start = matches[0]
        # Find the end of this section: advance to the next markdown header or EOF.
        # We look for "\n#" patterns that indicate a new section at the same or higher
        # level, starting just after the anchor header line itself.
        next_header_index = -1
        search_cursor = start + len(prefix_text)
        for pattern in ("\n##", "\n#"):
            candidate = content.find(pattern, search_cursor)
            if candidate != -1:
                if next_header_index == -1 or candidate < next_header_index:
                    next_header_index = candidate

        end = next_header_index if next_header_index != -1 else len(content)
        return start, end
    excerpt = _build_excerpt(content, max_length=400)
    return 0, len(excerpt)


def _serialize_workspace_documents(documents: Iterable[dict[str, Any]]) -> list[CopilotToolDocumentOut]:
    serialized_documents: list[CopilotToolDocumentOut] = []
    for document in documents:
        if not document.get("ai_readable", True) or document.get("hidden_from_agent", False):
            continue
        serialized_documents.append(
            CopilotToolDocumentOut(
                document_id=str(document["document_id"]),
                title=document["title"],
                type=document["type"],
                status=document["status"],
                source=document["source"],
                ai_writable=bool(document.get("ai_writable", False)),
                version=int(document.get("version") or 1),
                updated_at=document["updated_at"],
                is_active=document.get("is_active", False),
                is_open=document.get("is_open", False),
                pinned_for_agent=document.get("pinned_for_agent", False),
            )
        )
    return serialized_documents


def _match_score(content: str, query: str) -> float:
    count = content.lower().count(query.lower())
    if count <= 0:
        return 0.0
    return round(min(1.0, 0.25 + ((count * len(query)) / max(len(content), 1))), 3)


def _document_type_allowed(document: Document, allowed_types: list[str]) -> bool:
    return not allowed_types or document.kind in set(allowed_types)


def _require_valid_claims(payload, claims: dict[str, Any]) -> None:
    _validate_tool_request(
        claims=claims,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )


@router.post("/open-documents", response_model=CopilotListOpenDocumentsOut)
async def list_open_documents_tool(
    payload: CopilotListOpenDocumentsIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotListOpenDocumentsOut:
    _require_valid_claims(payload, claims)
    await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=payload.user_id)
    open_document_ids = set(payload.workspace_index.open_document_ids)
    visible_documents = [
        document
        for document in payload.workspace_index.documents
        if document.document_id in open_document_ids or document.is_active
    ]
    return CopilotListOpenDocumentsOut(
        documents=_serialize_workspace_documents(
            [document.model_dump(mode="python") for document in visible_documents]
        )
    )


@router.post("/encounter-documents", response_model=CopilotListEncounterDocumentsOut)
async def list_encounter_documents_tool(
    payload: CopilotListEncounterDocumentsIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotListEncounterDocumentsOut:
    _require_valid_claims(payload, claims)
    await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=payload.user_id)
    documents = await _get_encounter_documents(session, encounter_id=payload.encounter_id, user_id=payload.user_id)
    return CopilotListEncounterDocumentsOut(
        documents=[
            CopilotToolDocumentOut(
                document_id=str(document.id),
                title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
                type=document.kind,
                status="final" if document.kind == "transcription" else "draft",
                source="transcription" if document.kind == "transcription" else "user",
                ai_writable=_document_ai_writable(document.kind),
                version=_document_version(document),
                updated_at=document.created_on.isoformat(),
            )
            for document in documents
        ]
    )


@router.post("/read-document", response_model=CopilotReadDocumentOut)
async def read_document_tool(
    payload: CopilotReadDocumentIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotReadDocumentOut:
    _require_valid_claims(payload, claims)
    document = await _get_owned_document(
        session,
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    sections_payload = _document_sections_payload(document)
    content = document.content_markdown or ""
    return CopilotReadDocumentOut(
        document_id=str(document.id),
        encounter_id=str(document.encounter_id),
        title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        type=document.kind,
        version=_document_version(document),
        content_hash=_content_hash(content),
        updated_at=document.created_on.isoformat(),
        mode=payload.mode,
        content=content,
        structure_mode=sections_payload["structure_mode"],
        sections=sections_payload["sections"],
    )


@router.post("/read-document-summary", response_model=CopilotReadDocumentSummaryOut)
async def read_document_summary_tool(
    payload: CopilotReadDocumentSummaryIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotReadDocumentSummaryOut:
    _require_valid_claims(payload, claims)
    document = await _get_owned_document(
        session,
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    sections_payload = _document_sections_payload(document)
    return CopilotReadDocumentSummaryOut(
        document_id=str(document.id),
        encounter_id=str(document.encounter_id),
        title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        type=document.kind,
        version=_document_version(document),
        content_hash=_content_hash(document.content_markdown or ""),
        updated_at=document.created_on.isoformat(),
        structure_mode=sections_payload["structure_mode"],
        sections=sections_payload["sections"],
    )


@router.post("/read-document-span", response_model=CopilotReadDocumentSpanOut)
async def read_document_span_tool(
    payload: CopilotReadDocumentSpanIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotReadDocumentSpanOut:
    _require_valid_claims(payload, claims)
    document = await _get_owned_document(
        session,
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    content = document.content_markdown or ""
    start, end = _find_anchor_span(
        content=content,
        exact_text=payload.exact_text,
        prefix_text=payload.prefix_text,
        suffix_text=payload.suffix_text,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
    )
    if end - start > payload.max_chars:
        end = min(len(content), start + payload.max_chars)
    return CopilotReadDocumentSpanOut(
        document_id=str(document.id),
        title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        type=document.kind,
        version=_document_version(document),
        content_hash=_content_hash(content),
        content=content[start:end],
        start_offset=start,
        end_offset=end,
        anchor=_anchor_for_span(content, start, end),
    )


@router.post("/search-documents", response_model=CopilotSearchDocumentsOut)
async def search_documents_tool(
    payload: CopilotSearchDocumentsIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotSearchDocumentsOut:
    _require_valid_claims(payload, claims)
    await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=payload.user_id)
    query = payload.query.strip()
    if not query:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La busqueda no puede estar vacia")
    result = await session.execute(
        select(Document)
        .options(selectinload(Document.doctor_template))
        .where(
            Document.encounter_id == payload.encounter_id,
            Document.doctor_id == payload.user_id,
            func.lower(Document.content_markdown).contains(query.lower()),
        )
        .order_by(Document.created_on, Document.id)
    )
    matches: list[CopilotSearchDocumentMatchOut] = []
    for document in result.scalars().all():
        if not _document_type_allowed(document, payload.allowed_document_types):
            continue
        content = document.content_markdown or ""
        start = content.lower().find(query.lower())
        if start < 0:
            continue
        end = start + len(query)
        matches.append(
            CopilotSearchDocumentMatchOut(
                document_id=str(document.id),
                title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
                type=document.kind,
                updated_at=document.created_on.isoformat(),
                snippet=_build_excerpt(content, query=query),
                score=_match_score(content, query),
                anchor=_anchor_for_span(content, start, end),
            )
        )
        if len(matches) >= payload.max_results:
            break
    return CopilotSearchDocumentsOut(query=query, matches=matches)


@router.post("/read-patch-history", response_model=CopilotReadPatchHistoryOut)
async def read_patch_history_tool(
    payload: CopilotReadPatchHistoryIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotReadPatchHistoryOut:
    _require_valid_claims(payload, claims)
    await _get_owned_document(
        session,
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    result = await session.execute(
        select(CopilotPatch)
        .where(
            CopilotPatch.target_document_id == payload.document_id,
            CopilotPatch.encounter_id == payload.encounter_id,
            CopilotPatch.doctor_id == payload.user_id,
        )
        .order_by(CopilotPatch.created_at.desc())
        .limit(payload.limit)
    )
    return CopilotReadPatchHistoryOut(
        document_id=str(payload.document_id),
        patches=[
            {
                "patch_id": patch.patch_id,
                "operation_type": patch.operation_type,
                "status": patch.status,
                "rationale": patch.rationale,
                "created_at": patch.created_at,
            }
            for patch in result.scalars().all()
        ],
    )


@router.post("/read-encounter-context", response_model=CopilotEncounterContextOut)
async def read_encounter_context_tool(
    payload: CopilotReadEncounterContextIn,
    claims: dict[str, Any] = Depends(require_copilot_tools_jwt),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotEncounterContextOut:
    _require_valid_claims(payload, claims)
    encounter = await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=payload.user_id)
    return CopilotEncounterContextOut(
        encounter_id=str(encounter.id),
        encounter_name=encounter.encounter_name,
        occurred_at=encounter.occurred_at.isoformat() if encounter.occurred_at else None,
        has_been_transcribed=encounter.has_been_transcribed,
        patient_id=str(encounter.patient_id) if encounter.patient_id else None,
        patient_summary=encounter.patient.summary if encounter.patient else None,
    )
