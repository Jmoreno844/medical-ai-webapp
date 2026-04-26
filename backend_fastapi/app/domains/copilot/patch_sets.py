from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CopilotPatch, CopilotPatchSet, CopilotRun, Document
from app.domains.documents.content import set_document_content_fields

MAX_PATCHES_PER_SET = 12
PATCH_TYPE_REWRITE_DOCUMENT = "rewrite_document"
PATCH_TYPE_REPLACE_SPAN = "replace_span"
PATCH_TYPE_INSERT_BEFORE = "insert_before"
PATCH_TYPE_INSERT_AFTER = "insert_after"
PATCH_TYPE_INSERT_AFTER_LEGACY = "insert_after_span"
PATCH_TYPE_DELETE_SPAN = "delete_span"
_ANCHOR_WINDOW_MULTIPLIER = 3


class CopilotPatchSetError(Exception):
    pass


class CopilotPatchSetConflictError(CopilotPatchSetError):
    pass


@dataclass(frozen=True)
class CopilotPatchSetApplyResult:
    patch_set_id: str
    document_id: str
    content: str
    applied_version: int
    applied_patch_ids: list[str]
    stale_patch_set_ids: list[str]
    stale_patch_ids: list[str]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace runs into a single space and strip edges."""
    return " ".join(text.split())


def _prefix_matches(content: str, index: int, prefix_text: str) -> bool:
    """Check if *prefix_text* plausibly ends the text just before *index*.

    The LLM may drop leading bullet markers, newlines, or extra spaces, so we
    take a wider window and compare after whitespace normalisation.
    """
    window_size = max(len(prefix_text) * _ANCHOR_WINDOW_MULTIPLIER, 30)
    return _normalize_ws(content[max(0, index - window_size) : index]).endswith(
        _normalize_ws(prefix_text)
    )


def _suffix_matches(content: str, after_index: int, suffix_text: str) -> bool:
    """Check if *suffix_text* plausibly starts the text right after the match."""
    window_size = max(len(suffix_text) * _ANCHOR_WINDOW_MULTIPLIER, 30)
    return _normalize_ws(content[after_index : after_index + window_size]).startswith(
        _normalize_ws(suffix_text)
    )


def resolve_anchor_span(content: str, anchor: dict[str, Any]) -> tuple[int, int]:
    exact_text = str(anchor.get("exactText") or "")
    prefix_text = anchor.get("prefixText")
    suffix_text = anchor.get("suffixText")
    start_offset = anchor.get("startOffset")
    end_offset = anchor.get("endOffset")
    if (
        isinstance(start_offset, int)
        and isinstance(end_offset, int)
        and 0 <= start_offset <= end_offset <= len(content)
        and (not exact_text or content[start_offset:end_offset] == exact_text)
    ):
        return start_offset, end_offset
    if not exact_text:
        raise CopilotPatchSetConflictError("El patch no tiene exactText para resolver el anchor")

    occurrences: list[int] = []
    cursor = 0
    while True:
        index = content.find(exact_text, cursor)
        if index == -1:
            break
        occurrences.append(index)
        cursor = index + 1
    if not occurrences:
        raise CopilotPatchSetConflictError("El anchor ya no coincide con el documento actual")
    if len(occurrences) == 1:
        start = occurrences[0]
        return start, start + len(exact_text)

    narrowed = [
        index
        for index in occurrences
        if (not isinstance(prefix_text, str) or _prefix_matches(content, index, prefix_text))
        and (
            not isinstance(suffix_text, str)
            or _suffix_matches(content, index + len(exact_text), suffix_text)
        )
    ]
    if len(narrowed) != 1:
        raise CopilotPatchSetConflictError(
            "El anchor es ambiguo o ya no coincide de forma unica con el documento actual"
        )
    start = narrowed[0]
    return start, start + len(exact_text)


def _normalize_patch_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == PATCH_TYPE_INSERT_AFTER_LEGACY:
        return PATCH_TYPE_INSERT_AFTER
    if normalized == PATCH_TYPE_REWRITE_DOCUMENT:
        return PATCH_TYPE_REPLACE_SPAN
    if normalized in {
        PATCH_TYPE_REPLACE_SPAN,
        PATCH_TYPE_INSERT_BEFORE,
        PATCH_TYPE_INSERT_AFTER,
        PATCH_TYPE_DELETE_SPAN,
    }:
        return normalized
    raise CopilotPatchSetConflictError(f"Tipo de patch no soportado: {value}")


def _normalize_patch_preview(preview: dict[str, Any]) -> dict[str, Any]:
    patch_type = _normalize_patch_type(
        preview.get("patch_type") or preview.get("type") or preview.get("operation_type")
    )
    return {
        "patch_id": str(preview["patch_id"]),
        "patch_type": patch_type,
        "operation_type": str(preview.get("operation_type") or patch_type),
        "order_index": int(preview.get("order_index") or 0),
        "anchor": preview.get("anchor") or {},
        "expected_hash": preview.get("expected_hash"),
        "replacement_text": preview.get("replacement_text"),
        "inserted_text": preview.get("inserted_text"),
        "old_text": preview.get("old_text"),
        "new_text": preview.get("new_text"),
        "document_preview_after": preview.get("document_preview_after"),
        "content_preview": str(
            preview.get("content_preview")
            or preview.get("document_preview_after")
            or preview.get("replacement_text")
            or preview.get("inserted_text")
            or preview.get("new_text")
            or ""
        ),
        "rationale": preview.get("rationale"),
        "confidence": preview.get("confidence"),
        "section": preview.get("section"),
    }


def _require_text(value: Any, *, field_name: str, operation_type: str) -> str:
    if not isinstance(value, str):
        raise CopilotPatchSetConflictError(f"{field_name} es requerido para {operation_type}")
    return value


def _replacement_repeats_anchor_context(
    *,
    replacement_text: str,
    anchor: dict[str, Any],
) -> str | None:
    normalized_replacement = _normalize_ws(replacement_text)
    prefix_text = anchor.get("prefixText")
    suffix_text = anchor.get("suffixText")

    if isinstance(prefix_text, str):
        normalized_prefix = _normalize_ws(prefix_text)
        if normalized_prefix and normalized_replacement.startswith(normalized_prefix):
            return "replacement_repeats_prefix"

    if isinstance(suffix_text, str):
        normalized_suffix = _normalize_ws(suffix_text)
        if normalized_suffix and normalized_replacement.endswith(normalized_suffix):
            return "replacement_repeats_suffix"

    return None


def _resolve_patch_against_document(*, preview: dict[str, Any], document_content: str) -> dict[str, Any]:
    patch = _normalize_patch_preview(preview)
    patch_type = patch["patch_type"]
    anchor = patch["anchor"]
    if patch["operation_type"] == PATCH_TYPE_REWRITE_DOCUMENT:
        new_text = _require_text(
            patch.get("replacement_text"),
            field_name="replacement_text",
            operation_type=PATCH_TYPE_REWRITE_DOCUMENT,
        )
        return {
            **patch,
            "resolved_start": 0,
            "resolved_end": len(document_content),
            "old_text": document_content,
            "new_text": new_text,
            "content_preview": new_text,
            "status": "pending",
            "conflict_reason": None,
        }

    start, end = resolve_anchor_span(document_content, patch["anchor"])
    old_text = document_content[start:end]
    if patch_type == PATCH_TYPE_DELETE_SPAN:
        new_text = ""
    elif patch_type in (PATCH_TYPE_INSERT_AFTER, PATCH_TYPE_INSERT_BEFORE):
        new_text = _require_text(
            patch.get("inserted_text"),
            field_name="inserted_text",
            operation_type=patch_type,
        )
    elif patch_type == PATCH_TYPE_REPLACE_SPAN:
        new_text = _require_text(
            patch.get("replacement_text"),
            field_name="replacement_text",
            operation_type=patch_type,
        )
        repeated_context = _replacement_repeats_anchor_context(
            replacement_text=new_text,
            anchor=anchor,
        )
        if repeated_context:
            raise CopilotPatchSetConflictError(repeated_context)
        if new_text == old_text:
            raise CopilotPatchSetConflictError("patch_without_change")
    else:
        raise CopilotPatchSetConflictError(f"Tipo de patch no soportado: {patch_type}")

    return {
        **patch,
        "resolved_start": start,
        "resolved_end": end,
        "old_text": old_text,
        "new_text": str(new_text),
        "content_preview": str(new_text),
        "status": "pending",
        "conflict_reason": None,
    }


def _mark_patch_conflict(patch: dict[str, Any], reason: str) -> dict[str, Any]:
    conflicted = dict(patch)
    conflicted["status"] = "conflicted"
    conflicted["conflict_reason"] = reason
    return conflicted


def _detect_internal_conflicts(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [dict(patch) for patch in patches]
    indexed = sorted(
        enumerate(normalized),
        key=lambda item: (
            item[1].get("resolved_start") or 0,
            item[1].get("resolved_end") or 0,
            item[1].get("order_index") or 0,
        ),
    )
    for cursor, (left_index, left_patch) in enumerate(indexed):
        if left_patch.get("status") == "conflicted":
            continue
        left_start = left_patch.get("resolved_start")
        left_end = left_patch.get("resolved_end")
        if left_start is None or left_end is None:
            normalized[left_index] = _mark_patch_conflict(left_patch, "missing_resolved_range")
            continue
        for right_index, right_patch in indexed[cursor + 1 :]:
            if right_patch.get("status") == "conflicted":
                continue
            right_start = right_patch.get("resolved_start")
            right_end = right_patch.get("resolved_end")
            if right_start is None or right_end is None:
                normalized[right_index] = _mark_patch_conflict(right_patch, "missing_resolved_range")
                continue
            overlaps = right_start < left_end and right_end > left_start
            same_anchor_point = (
                left_start == left_end == right_start == right_end
                and left_patch.get("patch_type") in {PATCH_TYPE_INSERT_BEFORE, PATCH_TYPE_INSERT_AFTER}
                and right_patch.get("patch_type") in {PATCH_TYPE_INSERT_BEFORE, PATCH_TYPE_INSERT_AFTER}
            )
            if overlaps and not same_anchor_point:
                normalized[left_index] = _mark_patch_conflict(normalized[left_index], "overlapping")
                normalized[right_index] = _mark_patch_conflict(normalized[right_index], "overlapping")
    return normalized


def _apply_patches_to_content(content: str, patches: list[dict[str, Any]]) -> str:
    ordered = sorted(
        patches,
        key=lambda patch: (
            patch["resolved_start"],
            patch["resolved_end"],
            patch.get("order_index") or 0,
        ),
    )
    cursor = 0
    result_parts: list[str] = []
    for patch in ordered:
        start = int(patch["resolved_start"])
        end = int(patch["resolved_end"])
        new_text = str(patch.get("new_text") or "")
        if start < cursor:
            raise CopilotPatchSetConflictError(
                "Los patches aceptados se superponen y no se pueden aplicar con seguridad"
            )
        if patch["patch_type"] == PATCH_TYPE_REPLACE_SPAN:
            result_parts.append(content[cursor:start])
            result_parts.append(new_text)
            cursor = end
        elif patch["patch_type"] == PATCH_TYPE_DELETE_SPAN:
            result_parts.append(content[cursor:start])
            cursor = end
        elif patch["patch_type"] == PATCH_TYPE_INSERT_BEFORE:
            result_parts.append(content[cursor:start])
            result_parts.append(new_text)
            result_parts.append(content[start:end])
            cursor = end
        elif patch["patch_type"] == PATCH_TYPE_INSERT_AFTER:
            result_parts.append(content[cursor:end])
            result_parts.append(new_text)
            cursor = end
        else:
            raise CopilotPatchSetConflictError(
                f"Operacion de patch no soportada en apply: {patch['patch_type']}"
            )
    result_parts.append(content[cursor:])
    return "".join(result_parts)


def _update_patch_set_status_from_children(patches: list[CopilotPatch], patch_set_status: str) -> str:
    if patch_set_status == "stale":
        return "stale"
    if not patches:
        return "rejected"
    statuses = {patch.status for patch in patches}
    if statuses <= {"rejected", "conflicted"}:
        return "rejected"
    if "pending" in statuses:
        return "pending"
    if statuses <= {"accepted"}:
        return "accepted"
    if "accepted" in statuses and statuses <= {"accepted", "rejected", "conflicted"}:
        return "partially_accepted"
    if "applied" in statuses and statuses <= {"applied"}:
        return "applied"
    if "applied" in statuses:
        return "partially_accepted"
    return patch_set_status


async def _load_patch_set_patches(session: AsyncSession, patch_set: CopilotPatchSet) -> list[CopilotPatch]:
    result = await session.execute(
        select(CopilotPatch).where(CopilotPatch.patch_set_id == patch_set.id).order_by(CopilotPatch.order_index, CopilotPatch.created_at)
    )
    return list(result.scalars().all())


async def persist_patch_set_preview(
    session: AsyncSession,
    *,
    run: CopilotRun,
    target_document: Document,
    patch_set_preview: dict[str, Any],
    user_id: int,
    encounter_id: int,
) -> CopilotPatchSet:
    patch_previews = list(patch_set_preview.get("patches") or [])
    if not patch_previews:
        raise CopilotPatchSetConflictError("El patch set no contiene patches revisables")
    if len(patch_previews) > MAX_PATCHES_PER_SET:
        raise CopilotPatchSetConflictError(
            f"El patch set excede el maximo permitido de {MAX_PATCHES_PER_SET} patches"
        )

    now = _now()
    current_content = target_document.content_markdown or ""
    base_hash = str(patch_set_preview["base_hash"])
    patch_set_status = "stale" if content_hash(current_content) != base_hash else "pending"
    result = await session.execute(
        select(CopilotPatchSet).where(
            CopilotPatchSet.patch_set_id == str(patch_set_preview["patch_set_id"])
        )
    )
    patch_set = result.scalar_one_or_none()
    if patch_set is None:
        patch_set = CopilotPatchSet(
            patch_set_id=str(patch_set_preview["patch_set_id"]),
            created_at=now,
        )
        session.add(patch_set)

    patch_set.run = run
    patch_set.encounter_id = encounter_id
    patch_set.doctor_id = user_id
    patch_set.target_document = target_document
    patch_set.base_version = int(patch_set_preview["base_version"])
    patch_set.base_hash = base_hash
    patch_set.rationale = patch_set_preview.get("rationale")
    patch_set.source_context_document_ids = [
        str(document_id) for document_id in patch_set_preview.get("source_context_document_ids", [])
    ]
    patch_set.target_document_title = patch_set_preview.get("target_document_title")
    patch_set.target_selection_reason = patch_set_preview.get("target_selection_reason")
    patch_set.document_preview_after = patch_set_preview.get("document_preview_after")
    patch_set.status = patch_set_status
    # Campos del plan clínico. Pueden ser None para ediciones simples que no
    # llamaron set_edit_plan. El frontend los usa para badges de alcance clínico.
    patch_set.edit_scope = patch_set_preview.get("edit_scope")
    patch_set.clinical_impact_level = patch_set_preview.get("clinical_impact_level")
    patch_set.affected_sections = list(patch_set_preview.get("affected_sections") or [])
    patch_set.review_comment = None
    patch_set.updated_at = now
    await session.flush()

    resolved_patches: list[dict[str, Any]] = []
    for preview in patch_previews:
        try:
            resolved = _resolve_patch_against_document(preview=preview, document_content=current_content)
        except CopilotPatchSetConflictError as error:
            resolved = _mark_patch_conflict(_normalize_patch_preview(preview), str(error))
            resolved["resolved_start"] = None
            resolved["resolved_end"] = None
        if patch_set_status == "stale" and resolved["status"] == "pending":
            resolved["status"] = "stale"
            resolved["conflict_reason"] = "stale_document"
        resolved_patches.append(resolved)
    resolved_patches = _detect_internal_conflicts(resolved_patches)

    preview_after = patch_set.document_preview_after
    if preview_after is None:
        applicable = [patch for patch in resolved_patches if patch.get("status") == "pending"]
        try:
            preview_after = _apply_patches_to_content(current_content, applicable) if applicable else None
        except CopilotPatchSetConflictError:
            preview_after = None
    patch_set.document_preview_after = preview_after

    keep_patch_ids: list[str] = []
    for resolved in resolved_patches:
        keep_patch_ids.append(resolved["patch_id"])
        result = await session.execute(
            select(CopilotPatch).where(CopilotPatch.patch_id == resolved["patch_id"])
        )
        patch = result.scalar_one_or_none()
        if patch is None:
            patch = CopilotPatch(patch_id=resolved["patch_id"], created_at=now)
            session.add(patch)
        patch.patch_set = patch_set
        patch.run = run
        patch.encounter_id = encounter_id
        patch.doctor_id = user_id
        patch.target_document = target_document
        patch.base_version = patch_set.base_version
        patch.order_index = resolved["order_index"]
        patch.patch_type = resolved["patch_type"]
        patch.operation_type = resolved["operation_type"]
        patch.anchor = resolved["anchor"]
        patch.expected_hash = resolved.get("expected_hash")
        patch.replacement_text = resolved.get("replacement_text")
        patch.inserted_text = resolved.get("inserted_text")
        patch.old_text = resolved.get("old_text")
        patch.new_text = resolved.get("new_text")
        patch.resolved_start = resolved.get("resolved_start")
        patch.resolved_end = resolved.get("resolved_end")
        patch.confidence = resolved.get("confidence")
        patch.conflict_reason = resolved.get("conflict_reason")
        patch.document_preview_after = resolved.get("document_preview_after")
        patch.content_preview = resolved["content_preview"]
        patch.rationale = resolved.get("rationale")
        patch.source_context_document_ids = patch_set.source_context_document_ids
        patch.target_document_title = patch_set.target_document_title
        patch.target_selection_reason = patch_set.target_selection_reason
        # Sección semántica derivada del clinical_plan del copiloto.
        # None para patches de ediciones simples sin set_edit_plan.
        patch.section = resolved.get("section")
        patch.status = resolved["status"]
        patch.review_comment = None
        patch.updated_at = now

    await session.flush()
    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = "stale" if patch_set_status == "stale" else _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.updated_at = now
    return patch_set


async def accept_patch(
    session: AsyncSession,
    *,
    patch_set: CopilotPatchSet,
    patch: CopilotPatch,
    review_comment: str | None = None,
) -> CopilotPatch:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError("El patch set ya no admite cambios de review")
    if patch.patch_set_id != patch_set.id:
        raise CopilotPatchSetConflictError("El patch no pertenece al patch set indicado")
    if patch.status in {"conflicted", "applied", "stale"}:
        raise CopilotPatchSetConflictError("El patch no puede aceptarse en su estado actual")
    patch.status = "accepted"
    patch.review_comment = review_comment
    patch.updated_at = _now()
    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.review_comment = review_comment
    patch_set.updated_at = _now()
    await session.flush()
    return patch


async def reject_patch(
    session: AsyncSession,
    *,
    patch_set: CopilotPatchSet,
    patch: CopilotPatch,
    review_comment: str | None = None,
) -> CopilotPatch:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError("El patch set ya no admite cambios de review")
    if patch.patch_set_id != patch_set.id:
        raise CopilotPatchSetConflictError("El patch no pertenece al patch set indicado")
    if patch.status in {"applied", "stale"}:
        raise CopilotPatchSetConflictError("El patch no puede rechazarse en su estado actual")
    patch.status = "rejected"
    patch.review_comment = review_comment
    patch.updated_at = _now()
    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.review_comment = review_comment
    patch_set.updated_at = _now()
    await session.flush()
    return patch


async def accept_all_patches(
    session: AsyncSession, *, patch_set: CopilotPatchSet, review_comment: str | None = None
) -> CopilotPatchSet:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError("El patch set ya no admite cambios de review")
    await session.execute(
        update(CopilotPatch)
        .where(CopilotPatch.patch_set_id == patch_set.id, CopilotPatch.status == "pending")
        .values(status="accepted", review_comment=review_comment, updated_at=_now())
    )
    await session.flush()
    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.review_comment = review_comment
    patch_set.updated_at = _now()
    return patch_set


async def reject_all_patches(
    session: AsyncSession, *, patch_set: CopilotPatchSet, review_comment: str | None = None
) -> CopilotPatchSet:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError("El patch set ya no admite cambios de review")
    await session.execute(
        update(CopilotPatch)
        .where(
            CopilotPatch.patch_set_id == patch_set.id,
            CopilotPatch.status.notin_(["applied", "stale", "conflicted"]),
        )
        .values(status="rejected", review_comment=review_comment, updated_at=_now())
    )
    await session.flush()
    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.review_comment = review_comment
    patch_set.updated_at = _now()
    return patch_set


async def _mark_patch_set_stale(
    session: AsyncSession, *, patch_set: CopilotPatchSet, review_comment: str | None = None
) -> None:
    patch_set.status = "stale"
    patch_set.review_comment = review_comment
    patch_set.updated_at = _now()
    await session.execute(
        update(CopilotPatch)
        .where(
            CopilotPatch.patch_set_id == patch_set.id,
            CopilotPatch.status.notin_(["rejected", "applied"]),
        )
        .values(status="stale", review_comment=review_comment, updated_at=_now())
    )


async def apply_accepted_patch_set(
    session: AsyncSession,
    *,
    patch_set: CopilotPatchSet,
    document_version: int | None = None,
    review_comment: str | None = None,
) -> CopilotPatchSetApplyResult:
    if patch_set.status == "applied":
        raise CopilotPatchSetConflictError("El patch set ya fue aplicado")
    if patch_set.status == "stale":
        raise CopilotPatchSetConflictError("El patch set ya quedo stale")
    if document_version is not None and int(document_version) != patch_set.base_version:
        await _mark_patch_set_stale(session, patch_set=patch_set, review_comment=review_comment)
        raise CopilotPatchSetConflictError(
            "El patch set quedo stale porque el documento cambio desde que se propuso"
        )

    result = await session.execute(
        select(CopilotPatchSet)
        .options(selectinload(CopilotPatchSet.target_document), selectinload(CopilotPatchSet.patches))
        .where(CopilotPatchSet.id == patch_set.id)
    )
    patch_set = result.scalar_one()
    document = patch_set.target_document
    current_content = document.content_markdown or ""
    if content_hash(current_content) != patch_set.base_hash:
        await _mark_patch_set_stale(session, patch_set=patch_set, review_comment=review_comment)
        raise CopilotPatchSetConflictError(
            "El hash base del patch set ya no coincide con el documento actual"
        )
    patches = sorted(patch_set.patches, key=lambda item: (item.resolved_start or 0, item.resolved_end or 0, item.order_index, item.created_at))
    if any(patch.status == "pending" for patch in patches):
        raise CopilotPatchSetConflictError("Aun hay patches pendientes de decision dentro del patch set")
    accepted_patches = [patch for patch in patches if patch.status == "accepted"]
    if not accepted_patches:
        raise CopilotPatchSetConflictError("No hay patches aceptados para aplicar en este patch set")

    next_content = _apply_patches_to_content(
        current_content,
        [
            {
                "patch_id": patch.patch_id,
                "patch_type": patch.patch_type,
                "resolved_start": patch.resolved_start,
                "resolved_end": patch.resolved_end,
                "new_text": patch.new_text,
                "order_index": patch.order_index,
            }
            for patch in accepted_patches
        ],
    )
    set_document_content_fields(
        document,
        content_markdown=next_content,
        preferred_source="markdown",
    )
    applied_patch_ids = [patch.patch_id for patch in accepted_patches]
    for patch in accepted_patches:
        patch.status = "applied"
        patch.review_comment = review_comment
        patch.updated_at = _now()

    stale_result = await session.execute(
        select(CopilotPatchSet).where(
            CopilotPatchSet.target_document_id == patch_set.target_document_id,
            CopilotPatchSet.status.in_(["pending", "accepted", "partially_accepted"]),
            CopilotPatchSet.id != patch_set.id,
        )
    )
    stale_patch_sets = list(stale_result.scalars().all())
    stale_patch_set_ids = [item.patch_set_id for item in stale_patch_sets]
    if stale_patch_sets:
        stale_ids = [item.id for item in stale_patch_sets]
        stale_patch_result = await session.execute(
            select(CopilotPatch.patch_id).where(
                CopilotPatch.patch_set_id.in_(stale_ids),
                CopilotPatch.status.notin_(["rejected", "applied"]),
            )
        )
        stale_patch_ids = [str(item) for item in stale_patch_result.scalars().all()]
        await session.execute(
            update(CopilotPatchSet).where(CopilotPatchSet.id.in_(stale_ids)).values(status="stale", updated_at=_now())
        )
        await session.execute(
            update(CopilotPatch)
            .where(
                CopilotPatch.patch_set_id.in_(stale_ids),
                CopilotPatch.status.notin_(["rejected", "applied"]),
            )
            .values(status="stale", review_comment=review_comment, updated_at=_now())
        )
    else:
        stale_patch_ids = []

    patches = await _load_patch_set_patches(session, patch_set)
    patch_set.status = _update_patch_set_status_from_children(patches, patch_set.status)
    patch_set.review_comment = review_comment
    patch_set.document_preview_after = next_content
    patch_set.updated_at = _now()
    await session.flush()

    return CopilotPatchSetApplyResult(
        patch_set_id=patch_set.patch_set_id,
        document_id=str(document.id),
        content=document.content_markdown or "",
        applied_version=max(document_version or patch_set.base_version, patch_set.base_version) + 1,
        applied_patch_ids=applied_patch_ids,
        stale_patch_set_ids=stale_patch_set_ids,
        stale_patch_ids=stale_patch_ids,
    )
