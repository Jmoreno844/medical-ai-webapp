from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from django.db.models import QuerySet

from apps.copilot.models import CopilotPatch
from apps.documents.models import Document


class CopilotPatchApplyError(Exception):
    pass


class CopilotPatchConflictError(CopilotPatchApplyError):
    pass


@dataclass(frozen=True)
class CopilotPatchApplyResult:
    patch_id: str
    document_id: str
    content: str
    applied_version: int
    stale_patch_ids: list[str]


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_anchor_span(content: str, anchor: dict[str, Any]) -> tuple[int, int]:
    exact_text = str(anchor.get("exactText") or "")
    prefix_text = anchor.get("prefixText")
    suffix_text = anchor.get("suffixText")
    start_offset = anchor.get("startOffset")
    end_offset = anchor.get("endOffset")

    if (
        isinstance(start_offset, int)
        and isinstance(end_offset, int)
        and 0 <= start_offset <= end_offset <= len(content)
    ):
        if exact_text and content[start_offset:end_offset] == exact_text:
            return start_offset, end_offset

    if not exact_text:
        raise CopilotPatchConflictError("El patch no tiene exactText para resolver el anchor")

    occurrences: list[int] = []
    cursor = 0
    while True:
        index = content.find(exact_text, cursor)
        if index == -1:
            break
        occurrences.append(index)
        cursor = index + 1

    if not occurrences:
        raise CopilotPatchConflictError("El anchor ya no coincide con el documento actual")

    if len(occurrences) == 1:
        start = occurrences[0]
        return start, start + len(exact_text)

    narrowed: list[int] = []
    for index in occurrences:
        prefix_match = True
        suffix_match = True
        if isinstance(prefix_text, str):
            prefix_match = content[max(0, index - len(prefix_text)) : index] == prefix_text
        if isinstance(suffix_text, str):
            suffix_start = index + len(exact_text)
            suffix_match = (
                content[suffix_start : suffix_start + len(suffix_text)] == suffix_text
            )
        if prefix_match and suffix_match:
            narrowed.append(index)

    if len(narrowed) != 1:
        raise CopilotPatchConflictError(
            "El anchor es ambiguo o ya no coincide de forma unica con el documento actual"
        )

    start = narrowed[0]
    return start, start + len(exact_text)


def _apply_operation(
    *,
    document: Document,
    patch: CopilotPatch,
) -> str:
    if patch.operation_type == "replace_span":
        start, end = _resolve_anchor_span(document.content, patch.anchor or {})
        return f"{document.content[:start]}{patch.after_preview or ''}{document.content[end:]}"

    if patch.operation_type == "insert_after_span":
        start, end = _resolve_anchor_span(document.content, patch.anchor or {})
        return f"{document.content[:end]}{patch.after_preview or ''}{document.content[end:]}"

    if patch.operation_type == "rewrite_document":
        return patch.document_preview_after or patch.content_preview

    raise CopilotPatchConflictError(f"Operacion de patch no soportada: {patch.operation_type}")


def apply_copilot_patch(
    *,
    patch: CopilotPatch,
    document_version: int | None = None,
    review_comment: str | None = None,
) -> CopilotPatchApplyResult:
    if patch.status != "pending":
        raise CopilotPatchConflictError("El patch ya no esta pendiente de revision")

    if document_version is not None and int(document_version) != patch.base_version:
        patch.status = "stale"
        patch.review_comment = review_comment
        patch.save(update_fields=["status", "review_comment", "updated_at"])
        raise CopilotPatchConflictError(
            "El patch quedo stale porque el documento cambio desde que se propuso"
        )

    target_document = patch.target_document
    before_preview = patch.before_preview if isinstance(patch.before_preview, str) else None
    expected_hash = patch.expected_hash if isinstance(patch.expected_hash, str) else None
    if expected_hash and before_preview:
        current_hash = _content_hash(before_preview)
        if current_hash != expected_hash:
            patch.status = "stale"
            patch.review_comment = review_comment
            patch.save(update_fields=["status", "review_comment", "updated_at"])
            raise CopilotPatchConflictError(
                "El hash esperado del patch ya no coincide con el contexto de origen"
            )

    next_content = _apply_operation(document=target_document, patch=patch)
    target_document.content = next_content
    target_document.save(update_fields=["content"])

    stale_queryset: QuerySet[CopilotPatch] = CopilotPatch.objects.filter(
        target_document=patch.target_document,
        status="pending",
    ).exclude(pk=patch.pk)
    stale_patch_ids = list(stale_queryset.values_list("patch_id", flat=True))
    stale_queryset.update(status="stale")

    patch.status = "applied"
    patch.review_comment = review_comment
    patch.content_preview = patch.document_preview_after or next_content
    patch.save(update_fields=["status", "review_comment", "content_preview", "updated_at"])

    return CopilotPatchApplyResult(
        patch_id=patch.patch_id,
        document_id=str(target_document.id),
        content=target_document.content,
        applied_version=max(document_version or patch.base_version, patch.base_version) + 1,
        stale_patch_ids=stale_patch_ids,
    )
