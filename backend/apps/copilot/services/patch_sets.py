from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.copilot.models import CopilotPatch, CopilotPatchSet, CopilotRun
from apps.documents.models import Document
from apps.documents.services.rich_document_content import set_document_content_fields

MAX_PATCHES_PER_SET = 12
PATCH_TYPE_REWRITE_DOCUMENT = "rewrite_document"
PATCH_TYPE_REPLACE_SPAN = "replace_span"
PATCH_TYPE_INSERT_BEFORE = "insert_before"
PATCH_TYPE_INSERT_AFTER = "insert_after"
PATCH_TYPE_INSERT_AFTER_LEGACY = "insert_after_span"
PATCH_TYPE_DELETE_SPAN = "delete_span"


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


_ANCHOR_WINDOW_MULTIPLIER = 3


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace runs into a single space and strip edges."""
    return " ".join(text.split())


def _prefix_matches(content: str, index: int, prefix_text: str) -> bool:
    """Check if *prefix_text* plausibly ends the text just before *index*.

    The LLM may drop leading bullet markers, newlines, or extra spaces, so we
    take a wider window and compare after whitespace normalisation.
    """
    window_size = max(len(prefix_text) * _ANCHOR_WINDOW_MULTIPLIER, 30)
    window = content[max(0, index - window_size) : index]
    return _normalize_ws(window).endswith(_normalize_ws(prefix_text))


def _suffix_matches(content: str, after_index: int, suffix_text: str) -> bool:
    """Check if *suffix_text* plausibly starts the text right after the match."""
    window_size = max(len(suffix_text) * _ANCHOR_WINDOW_MULTIPLIER, 30)
    window = content[after_index : after_index + window_size]
    return _normalize_ws(window).startswith(_normalize_ws(suffix_text))


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
    ):
        if exact_text and content[start_offset:end_offset] == exact_text:
            return start_offset, end_offset

    if not exact_text:
        raise CopilotPatchSetConflictError(
            "El patch no tiene exactText para resolver el anchor"
        )

    occurrences: list[int] = []
    cursor = 0
    while True:
        index = content.find(exact_text, cursor)
        if index == -1:
            break
        occurrences.append(index)
        cursor = index + 1

    if not occurrences:
        raise CopilotPatchSetConflictError(
            "El anchor ya no coincide con el documento actual"
        )

    if len(occurrences) == 1:
        start = occurrences[0]
        return start, start + len(exact_text)

    narrowed: list[int] = []
    for index in occurrences:
        p_ok = True
        s_ok = True
        if isinstance(prefix_text, str):
            p_ok = _prefix_matches(content, index, prefix_text)
        if isinstance(suffix_text, str):
            s_ok = _suffix_matches(content, index + len(exact_text), suffix_text)
        if p_ok and s_ok:
            narrowed.append(index)

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
        preview.get("patch_type")
        or preview.get("type")
        or preview.get("operation_type")
    )
    operation_type = str(preview.get("operation_type") or patch_type)
    return {
        "patch_id": str(preview["patch_id"]),
        "patch_type": patch_type,
        "operation_type": operation_type,
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
    }


def _require_text(value: Any, *, field_name: str, operation_type: str) -> str:
    if not isinstance(value, str):
        raise CopilotPatchSetConflictError(
            f"{field_name} es requerido para {operation_type}"
        )
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


def _resolve_patch_against_document(
    *,
    preview: dict[str, Any],
    document_content: str,
) -> dict[str, Any]:
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

    start, end = resolve_anchor_span(document_content, anchor)
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
            normalized[left_index] = _mark_patch_conflict(
                left_patch, "missing_resolved_range"
            )
            continue
        for right_index, right_patch in indexed[cursor + 1 :]:
            if right_patch.get("status") == "conflicted":
                continue
            right_start = right_patch.get("resolved_start")
            right_end = right_patch.get("resolved_end")
            if right_start is None or right_end is None:
                normalized[right_index] = _mark_patch_conflict(
                    right_patch, "missing_resolved_range"
                )
                continue
            overlaps = right_start < left_end and right_end > left_start
            same_anchor_point = (
                left_start == left_end == right_start == right_end
                and left_patch.get("patch_type")
                in {PATCH_TYPE_INSERT_BEFORE, PATCH_TYPE_INSERT_AFTER}
                and right_patch.get("patch_type")
                in {PATCH_TYPE_INSERT_BEFORE, PATCH_TYPE_INSERT_AFTER}
            )
            if overlaps and not same_anchor_point:
                normalized[left_index] = _mark_patch_conflict(
                    normalized[left_index], "overlapping"
                )
                normalized[right_index] = _mark_patch_conflict(
                    normalized[right_index], "overlapping"
                )
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
        patch_type = patch["patch_type"]
        new_text = str(patch.get("new_text") or "")

        if start < cursor:
            raise CopilotPatchSetConflictError(
                "Los patches aceptados se superponen y no se pueden aplicar con seguridad"
            )

        if patch_type == PATCH_TYPE_REPLACE_SPAN:
            result_parts.append(content[cursor:start])
            result_parts.append(new_text)
            cursor = end
            continue

        if patch_type == PATCH_TYPE_DELETE_SPAN:
            result_parts.append(content[cursor:start])
            cursor = end
            continue

        if patch_type == PATCH_TYPE_INSERT_BEFORE:
            result_parts.append(content[cursor:start])
            result_parts.append(new_text)
            result_parts.append(content[start:end])
            cursor = end
            continue

        if patch_type == PATCH_TYPE_INSERT_AFTER:
            result_parts.append(content[cursor:end])
            result_parts.append(new_text)
            cursor = end
            continue

        raise CopilotPatchSetConflictError(
            f"Operacion de patch no soportada en apply: {patch_type}"
        )

    result_parts.append(content[cursor:])
    return "".join(result_parts)


def _preview_document_after(
    *,
    document_content: str,
    patches: list[dict[str, Any]],
) -> str | None:
    applicable = [patch for patch in patches if patch.get("status") == "pending"]
    if not applicable:
        return None
    try:
        return _apply_patches_to_content(document_content, applicable)
    except CopilotPatchSetConflictError:
        return None


def _update_patch_set_status_from_children(patch_set: CopilotPatchSet) -> str:
    patches = list(patch_set.patches.all())
    if patch_set.status == "stale":
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

    return patch_set.status


@transaction.atomic
def persist_patch_set_preview(
    *,
    run: CopilotRun,
    target_document: Document,
    patch_set_preview: dict[str, Any],
    user_id: int,
    encounter_id: int,
) -> CopilotPatchSet:
    patch_previews = list(patch_set_preview.get("patches") or [])
    if not patch_previews:
        raise CopilotPatchSetConflictError(
            "El patch set no contiene patches revisables"
        )
    if len(patch_previews) > MAX_PATCHES_PER_SET:
        raise CopilotPatchSetConflictError(
            f"El patch set excede el maximo permitido de {MAX_PATCHES_PER_SET} patches"
        )

    current_content = target_document.content
    base_hash = str(patch_set_preview["base_hash"])
    patch_set_status = "pending"
    if content_hash(current_content) != base_hash:
        patch_set_status = "stale"

    patch_set, _created = CopilotPatchSet.objects.update_or_create(
        patch_set_id=str(patch_set_preview["patch_set_id"]),
        defaults={
            "run": run,
            "encounter_id": encounter_id,
            "doctor_id": user_id,
            "target_document": target_document,
            "base_version": int(patch_set_preview["base_version"]),
            "base_hash": base_hash,
            "rationale": patch_set_preview.get("rationale"),
            "source_context_document_ids": [
                str(document_id)
                for document_id in patch_set_preview.get(
                    "source_context_document_ids", []
                )
            ],
            "target_document_title": patch_set_preview.get("target_document_title"),
            "target_selection_reason": patch_set_preview.get("target_selection_reason"),
            "document_preview_after": patch_set_preview.get("document_preview_after"),
            "status": patch_set_status,
            "review_comment": None,
            # Campos del plan clínico. Pueden ser None para ediciones simples que no
            # llamaron set_edit_plan. El frontend los usa para badges de alcance clínico.
            "edit_scope": patch_set_preview.get("edit_scope"),
            "clinical_impact_level": patch_set_preview.get("clinical_impact_level"),
            "affected_sections": list(patch_set_preview.get("affected_sections") or []),
        },
    )

    resolved_patches: list[dict[str, Any]] = []
    for preview in patch_previews:
        try:
            resolved = _resolve_patch_against_document(
                preview=preview,
                document_content=current_content,
            )
        except CopilotPatchSetConflictError as error:
            preview_patch = _normalize_patch_preview(preview)
            resolved = _mark_patch_conflict(preview_patch, str(error))
            resolved["resolved_start"] = None
            resolved["resolved_end"] = None
        if patch_set_status == "stale" and resolved["status"] == "pending":
            resolved["status"] = "stale"
            resolved["conflict_reason"] = "stale_document"
        resolved_patches.append(resolved)

    resolved_patches = _detect_internal_conflicts(resolved_patches)
    document_preview_after = (
        patch_set.document_preview_after
        or _preview_document_after(
            document_content=current_content,
            patches=resolved_patches,
        )
    )
    if document_preview_after != patch_set.document_preview_after:
        patch_set.document_preview_after = document_preview_after
        patch_set.save(update_fields=["document_preview_after", "updated_at"])

    keep_patch_ids: list[str] = []
    for resolved in resolved_patches:
        keep_patch_ids.append(resolved["patch_id"])
        CopilotPatch.objects.update_or_create(
            patch_id=resolved["patch_id"],
            defaults={
                "patch_set": patch_set,
                "run": run,
                "encounter_id": encounter_id,
                "doctor_id": user_id,
                "target_document": target_document,
                "base_version": int(patch_set.base_version),
                "order_index": resolved["order_index"],
                "patch_type": resolved["patch_type"],
                "operation_type": resolved["operation_type"],
                "anchor": resolved["anchor"],
                "expected_hash": resolved.get("expected_hash"),
                "replacement_text": resolved.get("replacement_text"),
                "inserted_text": resolved.get("inserted_text"),
                "old_text": resolved.get("old_text"),
                "new_text": resolved.get("new_text"),
                "resolved_start": resolved.get("resolved_start"),
                "resolved_end": resolved.get("resolved_end"),
                "confidence": resolved.get("confidence"),
                "conflict_reason": resolved.get("conflict_reason"),
                "document_preview_after": resolved.get("document_preview_after"),
                "content_preview": resolved["content_preview"],
                "rationale": resolved.get("rationale"),
                "source_context_document_ids": patch_set.source_context_document_ids,
                "target_document_title": patch_set.target_document_title,
                "target_selection_reason": patch_set.target_selection_reason,
                # Sección semántica derivada del clinical_plan del copiloto.
                # None para patches de ediciones simples sin set_edit_plan.
                "section": resolved.get("section"),
                "status": resolved["status"],
                "review_comment": None,
            },
        )

    patch_set.patches.exclude(patch_id__in=keep_patch_ids).delete()
    patch_set.status = _update_patch_set_status_from_children(patch_set)
    if patch_set_status == "stale":
        patch_set.status = "stale"
    patch_set.save(update_fields=["status", "updated_at"])
    return patch_set


def ensure_patch_set_for_legacy_patch(patch: CopilotPatch) -> CopilotPatchSet:
    if patch.patch_set_id:
        return patch.patch_set

    base_content = patch.old_text or patch.target_document.content
    patch_set, _created = CopilotPatchSet.objects.get_or_create(
        patch_set_id=f"legacy-{patch.patch_id}",
        defaults={
            "run": patch.run,
            "encounter": patch.encounter,
            "doctor": patch.doctor,
            "target_document": patch.target_document,
            "base_version": patch.base_version,
            "base_hash": content_hash(base_content),
            "rationale": patch.rationale,
            "source_context_document_ids": patch.source_context_document_ids,
            "target_document_title": patch.target_document_title,
            "target_selection_reason": patch.target_selection_reason,
            "document_preview_after": patch.document_preview_after
            or patch.content_preview,
            "status": "pending",
        },
    )
    patch.patch_set = patch_set
    if not patch.patch_type:
        patch.patch_type = _normalize_patch_type(patch.operation_type)
    if patch.resolved_start is None or patch.resolved_end is None:
        try:
            patch.resolved_start, patch.resolved_end = resolve_anchor_span(
                patch.target_document.content,
                patch.anchor or {},
            )
        except CopilotPatchSetConflictError:
            if patch.operation_type == PATCH_TYPE_REWRITE_DOCUMENT:
                patch.resolved_start = 0
                patch.resolved_end = len(patch.target_document.content)
            else:
                patch.status = "conflicted"
                patch.conflict_reason = "legacy_anchor_unresolved"
    patch.order_index = patch.order_index or 0
    patch.old_text = patch.old_text or (
        patch.target_document.content[patch.resolved_start : patch.resolved_end]
        if patch.resolved_start is not None and patch.resolved_end is not None
        else None
    )
    patch.new_text = (
        patch.new_text
        or patch.replacement_text
        or patch.inserted_text
        or patch.content_preview
    )
    patch.save(
        update_fields=[
            "patch_set",
            "patch_type",
            "resolved_start",
            "resolved_end",
            "status",
            "conflict_reason",
            "order_index",
            "old_text",
            "new_text",
            "updated_at",
        ]
    )
    return patch_set


def accept_patch(
    *,
    patch_set: CopilotPatchSet,
    patch: CopilotPatch,
    review_comment: str | None = None,
) -> CopilotPatch:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError(
            "El patch set ya no admite cambios de review"
        )
    if patch.patch_set_id != patch_set.id:
        raise CopilotPatchSetConflictError(
            "El patch no pertenece al patch set indicado"
        )
    if patch.status in {"conflicted", "applied", "stale"}:
        raise CopilotPatchSetConflictError(
            "El patch no puede aceptarse en su estado actual"
        )
    patch.status = "accepted"
    patch.review_comment = review_comment
    patch.save(update_fields=["status", "review_comment", "updated_at"])
    patch_set.status = _update_patch_set_status_from_children(patch_set)
    patch_set.review_comment = review_comment
    patch_set.save(update_fields=["status", "review_comment", "updated_at"])
    return patch


def reject_patch(
    *,
    patch_set: CopilotPatchSet,
    patch: CopilotPatch,
    review_comment: str | None = None,
) -> CopilotPatch:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError(
            "El patch set ya no admite cambios de review"
        )
    if patch.patch_set_id != patch_set.id:
        raise CopilotPatchSetConflictError(
            "El patch no pertenece al patch set indicado"
        )
    if patch.status in {"applied", "stale"}:
        raise CopilotPatchSetConflictError(
            "El patch no puede rechazarse en su estado actual"
        )
    patch.status = "rejected"
    patch.review_comment = review_comment
    patch.save(update_fields=["status", "review_comment", "updated_at"])
    patch_set.status = _update_patch_set_status_from_children(patch_set)
    patch_set.review_comment = review_comment
    patch_set.save(update_fields=["status", "review_comment", "updated_at"])
    return patch


def accept_all_patches(
    *, patch_set: CopilotPatchSet, review_comment: str | None = None
) -> CopilotPatchSet:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError(
            "El patch set ya no admite cambios de review"
        )
    patch_set.patches.filter(status="pending").exclude(status="conflicted").update(
        status="accepted",
        review_comment=review_comment,
    )
    patch_set.status = _update_patch_set_status_from_children(patch_set)
    patch_set.review_comment = review_comment
    patch_set.save(update_fields=["status", "review_comment", "updated_at"])
    return patch_set


def reject_all_patches(
    *, patch_set: CopilotPatchSet, review_comment: str | None = None
) -> CopilotPatchSet:
    if patch_set.status in {"stale", "applied"}:
        raise CopilotPatchSetConflictError(
            "El patch set ya no admite cambios de review"
        )
    patch_set.patches.exclude(status__in=["applied", "stale", "conflicted"]).update(
        status="rejected",
        review_comment=review_comment,
    )
    patch_set.status = _update_patch_set_status_from_children(patch_set)
    patch_set.review_comment = review_comment
    patch_set.save(update_fields=["status", "review_comment", "updated_at"])
    return patch_set


def _mark_patch_set_stale(
    *,
    patch_set: CopilotPatchSet,
    review_comment: str | None = None,
) -> None:
    patch_set.status = "stale"
    patch_set.review_comment = review_comment
    patch_set.save(update_fields=["status", "review_comment", "updated_at"])
    patch_set.patches.exclude(status__in=["rejected", "applied"]).update(
        status="stale",
        review_comment=review_comment,
    )


@transaction.atomic
def apply_accepted_patch_set(
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
        _mark_patch_set_stale(patch_set=patch_set, review_comment=review_comment)
        raise CopilotPatchSetConflictError(
            "El patch set quedo stale porque el documento cambio desde que se propuso"
        )

    document = patch_set.target_document
    current_hash = content_hash(document.content)
    if current_hash != patch_set.base_hash:
        _mark_patch_set_stale(patch_set=patch_set, review_comment=review_comment)
        raise CopilotPatchSetConflictError(
            "El hash base del patch set ya no coincide con el documento actual"
        )

    if patch_set.patches.filter(status="pending").exists():
        raise CopilotPatchSetConflictError(
            "Aun hay patches pendientes de decision dentro del patch set"
        )

    accepted_patches = list(
        patch_set.patches.filter(status="accepted").order_by(
            "resolved_start",
            "resolved_end",
            "order_index",
            "created_at",
        )
    )
    if not accepted_patches:
        raise CopilotPatchSetConflictError(
            "No hay patches aceptados para aplicar en este patch set"
        )

    patch_payloads = [
        {
            "patch_id": patch.patch_id,
            "patch_type": patch.patch_type,
            "resolved_start": patch.resolved_start,
            "resolved_end": patch.resolved_end,
            "new_text": patch.new_text,
            "order_index": patch.order_index,
        }
        for patch in accepted_patches
    ]
    next_content = _apply_patches_to_content(document.content, patch_payloads)
    set_document_content_fields(
        document,
        content_markdown=next_content,
        preferred_source="markdown",
    )
    document.save(update_fields=["content_markdown", "content_json"])

    applied_patch_ids = [patch.patch_id for patch in accepted_patches]
    patch_set.patches.filter(pk__in=[patch.pk for patch in accepted_patches]).update(
        status="applied",
        review_comment=review_comment,
    )

    stale_patch_sets = CopilotPatchSet.objects.filter(
        target_document=patch_set.target_document,
        status__in=["pending", "accepted", "partially_accepted"],
    ).exclude(pk=patch_set.pk)
    stale_patch_set_ids = list(stale_patch_sets.values_list("patch_set_id", flat=True))
    stale_patch_ids = list(
        CopilotPatch.objects.filter(patch_set__in=stale_patch_sets)
        .exclude(status__in=["rejected", "applied"])
        .values_list("patch_id", flat=True)
    )
    stale_patch_sets.update(status="stale")
    CopilotPatch.objects.filter(patch_set__in=stale_patch_sets).exclude(
        status__in=["rejected", "applied"]
    ).update(status="stale", review_comment=review_comment)

    patch_set.status = _update_patch_set_status_from_children(patch_set)
    patch_set.review_comment = review_comment
    patch_set.document_preview_after = next_content
    patch_set.save(
        update_fields=[
            "status",
            "review_comment",
            "document_preview_after",
            "updated_at",
        ]
    )

    return CopilotPatchSetApplyResult(
        patch_set_id=patch_set.patch_set_id,
        document_id=str(document.id),
        content=document.content_markdown,
        applied_version=max(
            document_version or patch_set.base_version, patch_set.base_version
        )
        + 1,
        applied_patch_ids=applied_patch_ids,
        stale_patch_set_ids=stale_patch_set_ids,
        stale_patch_ids=stale_patch_ids,
    )
