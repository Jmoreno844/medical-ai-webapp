from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.copilot.models import CopilotPatch
from apps.copilot.schemas import (
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
from apps.copilot.services.tools_auth import CopilotToolsJWTAuth
from apps.documents.models import Document
from apps.documents.services.document_sections import extract_document_sections
from apps.encounters.models import Encounter

router = Router(tags=["copilot-internal-tools"])

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


def _normalize_auth_claims(request) -> dict[str, str]:
    auth_payload = getattr(request, "auth", None)
    if not isinstance(auth_payload, dict):
        raise HttpError(401, "Token interno invalido")
    return {key: str(value) for key, value in auth_payload.items()}


def _validate_tool_request(
    request,
    *,
    run_id: str,
    thread_id: str,
    encounter_id: int,
    user_id: int,
) -> dict[str, str]:
    claims = _normalize_auth_claims(request)

    expected = {
        "run_id": run_id,
        "thread_id": thread_id,
        "encounter_id": str(encounter_id),
        "user_id": str(user_id),
    }
    for claim_name, expected_value in expected.items():
        if claims.get(claim_name) != expected_value:
            raise HttpError(403, f"Claim interno invalido para {claim_name}")

    return claims


def _get_owned_encounter(*, encounter_id: int, user_id: int) -> Encounter:
    encounter = get_object_or_404(
        Encounter.objects.select_related("patient"),
        id=encounter_id,
    )
    if encounter.doctor_id != user_id:
        raise HttpError(403, "No tienes permiso para acceder a este encuentro")
    return encounter


def _get_encounter_documents(*, encounter_id: int, user_id: int) -> QuerySet[Document]:
    return Document.objects.filter(
        encounter_id=encounter_id, doctor_id=user_id
    ).select_related("doctor_template").order_by(
        "created_on",
        "id",
    )


def _get_owned_document(
    *, document_id: int, encounter_id: int, user_id: int
) -> Document:
    document = get_object_or_404(
        Document.objects.select_related("doctor_template"), id=document_id
    )
    if document.encounter_id != encounter_id or document.doctor_id != user_id:
        raise HttpError(403, "No tienes permiso para acceder a este documento")
    return document


def _document_sections_payload(document: Document) -> dict[str, Any]:
    return extract_document_sections(
        content_markdown=document.content,
        content_json=getattr(document, "content_json", None),
    )


def _document_title(kind: str, document_id: int, *, template_name: str | None = None) -> str:
    if template_name and kind in ("note", "template"):
        return template_name
    return DOCUMENT_TITLES.get(kind, f"Documento {document_id}")


def _build_excerpt(
    content: str, *, query: str | None = None, max_length: int = 240
) -> str:
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


def _document_version(document: Document) -> int:
    return 1


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _anchor_for_span(content: str, start: int, end: int) -> dict[str, Any]:
    prefix_start = max(0, start - 48)
    suffix_end = min(len(content), end + 48)
    return {
        "exactText": content[start:end],
        "prefixText": content[prefix_start:start],
        "suffixText": content[end:suffix_end],
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
    if (
        start_offset is not None
        and end_offset is not None
        and 0 <= start_offset <= end_offset <= len(content)
    ):
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
            raise HttpError(404, "No se encontro el span solicitado en el documento")

        if len(matches) == 1:
            start = matches[0]
            return start, start + len(exact_text)

        narrowed: list[int] = []
        for index in matches:
            prefix_match = True
            suffix_match = True
            if prefix_text is not None:
                prefix_match = (
                    content[max(0, index - len(prefix_text)) : index] == prefix_text
                )
            if suffix_text is not None:
                suffix_start = index + len(exact_text)
                suffix_match = (
                    content[suffix_start : suffix_start + len(suffix_text)]
                    == suffix_text
                )
            if prefix_match and suffix_match:
                narrowed.append(index)

        if len(narrowed) != 1:
            raise HttpError(
                409,
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
            raise HttpError(404, "No se encontro el prefix_text solicitado en el documento")
        if len(matches) > 1:
            raise HttpError(409, "El prefix_text es ambiguo: aparece mas de una vez en el documento")

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


def _serialize_workspace_documents(
    documents: Iterable[dict],
) -> list[CopilotToolDocumentOut]:
    serialized_documents: list[CopilotToolDocumentOut] = []
    for document in documents:
        if not document.get("ai_readable", True) or document.get(
            "hidden_from_agent", False
        ):
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
    lowered_content = content.lower()
    lowered_query = query.lower()
    count = lowered_content.count(lowered_query)
    if count <= 0:
        return 0.0
    return round(
        min(1.0, 0.25 + ((count * len(lowered_query)) / max(len(content), 1))), 3
    )


def _document_type_allowed(document: Document, allowed_types: list[str]) -> bool:
    if not allowed_types:
        return True
    return document.kind in set(allowed_types)


def _context_category_for_document(document_kind: str) -> str:
    if document_kind == "transcription":
        return "symptom"
    if document_kind == "context":
        return "plan"
    return "diagnosis"


@router.post(
    "/internal/copilot/tools/open-documents",
    response=CopilotListOpenDocumentsOut,
    auth=CopilotToolsJWTAuth(),
)
def list_open_documents_tool(request, payload: CopilotListOpenDocumentsIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    _get_owned_encounter(encounter_id=payload.encounter_id, user_id=payload.user_id)

    open_document_ids = set(payload.workspace_index.open_document_ids)
    visible_documents = [
        document
        for document in payload.workspace_index.documents
        if document.document_id in open_document_ids or document.is_active
    ]

    return {
        "documents": _serialize_workspace_documents(
            [document.model_dump(mode="python") for document in visible_documents]
        )
    }


@router.post(
    "/internal/copilot/tools/encounter-documents",
    response=CopilotListEncounterDocumentsOut,
    auth=CopilotToolsJWTAuth(),
)
def list_encounter_documents_tool(request, payload: CopilotListEncounterDocumentsIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    _get_owned_encounter(encounter_id=payload.encounter_id, user_id=payload.user_id)

    documents = _get_encounter_documents(
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    return {
        "documents": [
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
    }


@router.post(
    "/internal/copilot/tools/read-document",
    response=CopilotReadDocumentOut,
    auth=CopilotToolsJWTAuth(),
)
def read_document_tool(request, payload: CopilotReadDocumentIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    document = _get_owned_document(
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    sections_payload = _document_sections_payload(document)

    return {
        "document_id": str(document.id),
        "encounter_id": str(document.encounter_id),
        "title": _document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        "type": document.kind,
        "version": _document_version(document),
        "content_hash": _content_hash(document.content),
        "updated_at": document.created_on.isoformat(),
        "mode": payload.mode,
        "content": document.content,
        "structure_mode": sections_payload["structure_mode"],
        "sections": sections_payload["sections"],
    }


@router.post(
    "/internal/copilot/tools/read-document-summary",
    response=CopilotReadDocumentSummaryOut,
    auth=CopilotToolsJWTAuth(),
)
def read_document_summary_tool(request, payload: CopilotReadDocumentSummaryIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    document = _get_owned_document(
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    sections_payload = _document_sections_payload(document)
    return {
        "document_id": str(document.id),
        "encounter_id": str(document.encounter_id),
        "title": _document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        "type": document.kind,
        "version": _document_version(document),
        "content_hash": _content_hash(document.content),
        "updated_at": document.created_on.isoformat(),
        "structure_mode": sections_payload["structure_mode"],
        "sections": sections_payload["sections"],
    }


@router.post(
    "/internal/copilot/tools/read-document-span",
    response=CopilotReadDocumentSpanOut,
    auth=CopilotToolsJWTAuth(),
)
def read_document_span_tool(request, payload: CopilotReadDocumentSpanIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    document = _get_owned_document(
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    start, end = _find_anchor_span(
        content=document.content,
        exact_text=payload.exact_text,
        prefix_text=payload.prefix_text,
        suffix_text=payload.suffix_text,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
    )
    if end - start > payload.max_chars:
        end = min(len(document.content), start + payload.max_chars)

    return {
        "document_id": str(document.id),
        "title": _document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
        "type": document.kind,
        "version": _document_version(document),
        "content_hash": _content_hash(document.content),
        "content": document.content[start:end],
        "start_offset": start,
        "end_offset": end,
        "anchor": _anchor_for_span(document.content, start, end),
    }


@router.post(
    "/internal/copilot/tools/search-documents",
    response=CopilotSearchDocumentsOut,
    auth=CopilotToolsJWTAuth(),
)
def search_documents_tool(request, payload: CopilotSearchDocumentsIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    _get_owned_encounter(encounter_id=payload.encounter_id, user_id=payload.user_id)

    query = payload.query.strip()
    if not query:
        raise HttpError(400, "La busqueda no puede estar vacia")

    documents = _get_encounter_documents(
        encounter_id=payload.encounter_id, user_id=payload.user_id
    ).filter(content__icontains=query)

    matches: list[CopilotSearchDocumentMatchOut] = []
    allowed_document_types = list(getattr(payload, "allowed_document_types", []) or [])
    for document in documents:
        if not _document_type_allowed(document, allowed_document_types):
            continue
        lowered_content = document.content.lower()
        lowered_query = query.lower()
        start = lowered_content.find(lowered_query)
        if start < 0:
            continue
        end = start + len(query)
        matches.append(
            CopilotSearchDocumentMatchOut(
                document_id=str(document.id),
                title=_document_title(document.kind, document.id, template_name=document.doctor_template.name if document.doctor_template else None),
                type=document.kind,
                updated_at=document.created_on.isoformat(),
                snippet=_build_excerpt(document.content, query=query),
                score=_match_score(document.content, query),
                anchor=_anchor_for_span(document.content, start, end),
            )
        )
        if len(matches) >= payload.max_results:
            break

    return {"query": query, "matches": matches}


@router.post(
    "/internal/copilot/tools/read-patch-history",
    response=CopilotReadPatchHistoryOut,
    auth=CopilotToolsJWTAuth(),
)
def read_patch_history_tool(request, payload: CopilotReadPatchHistoryIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    _get_owned_document(
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    patches = list(
        CopilotPatch.objects.filter(
            target_document_id=payload.document_id,
            encounter_id=payload.encounter_id,
            doctor_id=payload.user_id,
        ).order_by("-created_at")[: payload.limit]
    )
    return {
        "document_id": str(payload.document_id),
        "patches": [
            {
                "patch_id": patch.patch_id,
                "operation_type": patch.operation_type,
                "status": patch.status,
                "rationale": patch.rationale,
                "created_at": patch.created_at,
            }
            for patch in patches
        ],
    }


@router.post(
    "/internal/copilot/tools/read-encounter-context",
    response=CopilotEncounterContextOut,
    auth=CopilotToolsJWTAuth(),
)
def read_encounter_context_tool(request, payload: CopilotReadEncounterContextIn):
    _validate_tool_request(
        request,
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=payload.user_id,
    )
    encounter = _get_owned_encounter(
        encounter_id=payload.encounter_id, user_id=payload.user_id
    )

    return {
        "encounter_id": str(encounter.id),
        "encounter_name": encounter.encounter_name,
        "occurred_at": encounter.occurred_at.isoformat()
        if encounter.occurred_at
        else None,
        "has_been_transcribed": encounter.has_been_transcribed,
        "patient_id": str(encounter.patient_id) if encounter.patient_id else None,
        "patient_summary": encounter.patient.summary if encounter.patient else None,
    }
