from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from ninja import Router
from ninja.errors import HttpError
from ninja.security import django_auth

from apps.copilot.models import CopilotPatch, CopilotPatchSet, CopilotRun
from apps.copilot.schemas import (
    CopilotMessageIn,
    CopilotPatchDecisionIn,
    CopilotPatchOut,
    CopilotPatchSetDecisionIn,
    CopilotPatchSetOut,
    CopilotReviewIn,
    CopilotRunOut,
    CopilotSessionIn,
    CopilotSessionOut,
)
from apps.copilot.services.client import CopilotAgentClient, CopilotServiceError
from apps.copilot.services.patch_apply import (
    CopilotPatchConflictError,
    apply_copilot_patch,
)
from apps.copilot.services.patch_sets import (
    CopilotPatchSetConflictError,
    accept_all_patches,
    accept_patch,
    apply_accepted_patch_set,
    ensure_patch_set_for_legacy_patch,
    persist_patch_set_preview,
    reject_all_patches,
    reject_patch,
)
from apps.copilot.services.threads import build_thread_id, parse_thread_id, thread_belongs_to_scope
from apps.documents.models import Document
from apps.encounters.models import Encounter

logger = logging.getLogger(__name__)
router = Router(tags=["copilot"])

STREAM_DONE_RUN_STATUSES = {"completed", "failed", "waiting_review"}
PATCH_SET_PREVIEW_REQUIRED_FIELDS = {
    "patch_set_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "base_hash",
    "patches",
}


def _serialize_run(run: CopilotRun, remote_run: dict[str, Any] | None = None) -> dict[str, Any]:
    active_patch_set_id = None
    applied_patch_set_id = None
    applied_patch_id = None
    applied_document_id = None
    applied_content = None
    applied_version = None
    trace_metadata: dict[str, Any] = {}
    if remote_run:
        trace_metadata = remote_run.get("trace_metadata", {}) or {}
        active_patch_set_id = remote_run.get("active_patch_set_id")
        applied_patch_set_id = remote_run.get("applied_patch_set_id")
        applied_patch_id = remote_run.get("applied_patch_id")
        applied_document_id = remote_run.get("applied_document_id")
        applied_content = remote_run.get("applied_content")
        applied_version = remote_run.get("applied_version")
    if active_patch_set_id is None and hasattr(run, "patch_sets"):
        active_patch_set_id = (
            run.patch_sets.order_by("-created_at").values_list("patch_set_id", flat=True).first()
        )

    return {
        "run_id": run.run_id,
        "thread_id": run.thread_id,
        "status": remote_run.get("status", run.status) if remote_run else run.status,
        "intent": remote_run.get("intent", run.intent) if remote_run else run.intent,
        "requires_human_review": (
            remote_run.get("requires_human_review", run.requires_human_review)
            if remote_run
            else run.requires_human_review
        ),
        "active_patch_set_id": active_patch_set_id,
        "final_response": remote_run.get("final_response") if remote_run else None,
        "applied_patch_set_id": applied_patch_set_id,
        "applied_patch_id": applied_patch_id,
        "applied_document_id": applied_document_id,
        "applied_content": applied_content,
        "applied_version": applied_version,
        "trace_metadata": trace_metadata if remote_run else {},
    }


def _serialize_patch(patch: CopilotPatch) -> dict[str, Any]:
    return {
        "patch_id": patch.patch_id,
        "patch_set_id": patch.patch_set.patch_set_id if patch.patch_set_id else None,
        "run_id": patch.run.run_id,
        "target_document_id": str(patch.target_document_id),
        "base_version": patch.base_version,
        "order_index": patch.order_index,
        "patch_type": patch.patch_type,
        "operation_type": patch.operation_type,
        "anchor": getattr(patch, "anchor", {}) or {},
        "expected_hash": getattr(patch, "expected_hash", None),
        "old_text": getattr(patch, "old_text", None),
        "new_text": getattr(patch, "new_text", None),
        "resolved_start": getattr(patch, "resolved_start", None),
        "resolved_end": getattr(patch, "resolved_end", None),
        "confidence": getattr(patch, "confidence", None),
        "conflict_reason": getattr(patch, "conflict_reason", None),
        "before_preview": getattr(patch, "before_preview", None),
        "after_preview": getattr(patch, "after_preview", None),
        "document_preview_after": getattr(patch, "document_preview_after", None),
        "content_preview": patch.content_preview,
        "rationale": patch.rationale,
        "source_context_document_ids": patch.source_context_document_ids,
        "target_document_title": getattr(patch, "target_document_title", None),
        "target_selection_reason": getattr(patch, "target_selection_reason", None),
        "status": patch.status,
        "review_comment": patch.review_comment,
        "created_at": patch.created_at,
        "updated_at": patch.updated_at,
    }


def _serialize_patch_set(patch_set: CopilotPatchSet) -> dict[str, Any]:
    patches = patch_set.patches.select_related("run", "target_document").order_by(
        "order_index",
        "created_at",
    )
    return {
        "patch_set_id": patch_set.patch_set_id,
        "run_id": patch_set.run.run_id,
        "target_document_id": str(patch_set.target_document_id),
        "base_version": patch_set.base_version,
        "base_hash": patch_set.base_hash,
        "rationale": patch_set.rationale,
        "source_context_document_ids": patch_set.source_context_document_ids,
        "target_document_title": patch_set.target_document_title,
        "target_selection_reason": patch_set.target_selection_reason,
        "document_preview_after": patch_set.document_preview_after,
        "status": patch_set.status,
        "review_comment": patch_set.review_comment,
        "patches": [_serialize_patch(patch) for patch in patches],
        "created_at": patch_set.created_at,
        "updated_at": patch_set.updated_at,
    }


def _get_owned_encounter(*, encounter_id: int, user_id: int) -> Encounter:
    encounter = get_object_or_404(Encounter, id=encounter_id)
    if encounter.doctor_id != user_id:
        raise HttpError(403, "No tienes permiso para acceder a este encuentro")
    return encounter


def _get_owned_patch_set(*, patch_set_id: str, user_id: int) -> CopilotPatchSet:
    patch_set = get_object_or_404(CopilotPatchSet, patch_set_id=patch_set_id)
    if patch_set.doctor_id != user_id:
        raise HttpError(403, "No tienes permiso para acceder a este patch set")
    return patch_set


def _sync_run_from_remote(run: CopilotRun, remote_run: dict[str, Any]) -> CopilotRun:
    run.status = remote_run.get("status", run.status)
    run.intent = remote_run.get("intent", run.intent)
    run.requires_human_review = remote_run.get(
        "requires_human_review", run.requires_human_review
    )
    run.save(
        update_fields=[
            "status",
            "intent",
            "requires_human_review",
            "updated_at",
        ]
    )
    return run


def _normalize_legacy_patch_set_preview(remote_run: dict[str, Any]) -> dict[str, Any] | None:
    patch_preview = remote_run.get("patch_preview")
    if not patch_preview:
        return None
    return {
        "patch_set_id": remote_run.get("active_patch_set_id")
        or f"legacy-{patch_preview['patch_id']}",
        "target_document_id": patch_preview["target_document_id"],
        "target_document_title": patch_preview.get("target_document_title"),
        "target_selection_reason": patch_preview.get("target_selection_reason"),
        "base_version": patch_preview.get("base_version") or 1,
        "base_hash": patch_preview.get("base_hash") or patch_preview.get("expected_hash") or "",
        "rationale": patch_preview.get("rationale"),
        "source_context_document_ids": patch_preview.get("source_context_document_ids", []),
        "document_preview_after": patch_preview.get("document_preview_after")
        or patch_preview.get("content_preview"),
        "patches": [
            {
                "patch_id": patch_preview["patch_id"],
                "patch_type": patch_preview.get("patch_type")
                or patch_preview.get("operation_type"),
                "operation_type": patch_preview.get("operation_type"),
                "order_index": patch_preview.get("order_index") or 0,
                "anchor": patch_preview.get("anchor") or {},
                "expected_hash": patch_preview.get("expected_hash"),
                "old_text": patch_preview.get("old_text"),
                "new_text": patch_preview.get("new_text"),
                "before_preview": patch_preview.get("before_preview"),
                "after_preview": patch_preview.get("after_preview"),
                "document_preview_after": patch_preview.get("document_preview_after"),
                "content_preview": patch_preview.get("content_preview"),
                "rationale": patch_preview.get("rationale"),
                "confidence": patch_preview.get("confidence"),
            }
        ],
    }


def _get_remote_patch_set_preview(remote_run: dict[str, Any]) -> dict[str, Any] | None:
    return remote_run.get("patch_set_preview") or _normalize_legacy_patch_set_preview(remote_run)


def _validate_remote_patch_set_preview(remote_run: dict[str, Any]) -> dict[str, Any] | None:
    patch_set_preview = _get_remote_patch_set_preview(remote_run)
    if not patch_set_preview:
        if remote_run.get("requires_human_review") or remote_run.get("status") == "waiting_review":
            raise HttpError(
                502,
                "Copilot agent devolvio waiting_review sin un patch_set_preview valido.",
            )
        return None

    missing_fields = [
        field_name
        for field_name in PATCH_SET_PREVIEW_REQUIRED_FIELDS
        if not patch_set_preview.get(field_name)
    ]
    if missing_fields:
        raise HttpError(
            502,
            "Copilot agent devolvio un patch_set_preview incompleto: "
            + ", ".join(missing_fields),
        )

    if remote_run.get("status") != "waiting_review" or not remote_run.get(
        "requires_human_review"
    ):
        logger.error(
            "Copilot agent returned inconsistent edit flow for run %s: status=%s requires_human_review=%s",
            remote_run.get("run_id"),
            remote_run.get("status"),
            remote_run.get("requires_human_review"),
        )
        raise HttpError(
            502,
            "Copilot agent devolvio un patch set de edicion sin dejar el run en waiting_review.",
        )

    return patch_set_preview


def _persist_patch_set_preview(
    *,
    run: CopilotRun,
    remote_run: dict[str, Any],
    user_id: int,
    encounter_id: int,
) -> CopilotPatchSet | None:
    patch_set_preview = _validate_remote_patch_set_preview(remote_run)
    if not patch_set_preview:
        return None

    target_document_id = int(patch_set_preview["target_document_id"])
    target_document = get_object_or_404(
        Document,
        id=target_document_id,
        encounter_id=encounter_id,
        doctor_id=user_id,
    )
    try:
        return persist_patch_set_preview(
            run=run,
            target_document=target_document,
            patch_set_preview=patch_set_preview,
            user_id=user_id,
            encounter_id=encounter_id,
        )
    except CopilotPatchSetConflictError as error:
        raise HttpError(502, str(error)) from error


@router.post("/copilot/sessions", response=CopilotSessionOut, auth=django_auth)
def create_copilot_session(request, payload: CopilotSessionIn):
    _get_owned_encounter(encounter_id=payload.encounter_id, user_id=request.user.id)
    return {
        "thread_id": build_thread_id(
            encounter_id=payload.encounter_id,
            user_id=request.user.id,
        ),
        "capability": "read_only",
    }


@router.post("/copilot/messages", response=CopilotRunOut, auth=django_auth)
def create_copilot_message(request, payload: CopilotMessageIn):
    encounter = _get_owned_encounter(
        encounter_id=payload.encounter_id,
        user_id=request.user.id,
    )
    if parse_thread_id(payload.thread_id) is None:
        raise HttpError(400, "thread_id invalido")
    if not thread_belongs_to_scope(
        thread_id=payload.thread_id,
        encounter_id=payload.encounter_id,
        user_id=request.user.id,
    ):
        raise HttpError(403, "No tienes permiso para usar este thread")
    client = CopilotAgentClient()

    try:
        response = client.create_run(
            {
                "tenant_id": f"doctor:{request.user.id}",
                "user_id": str(request.user.id),
                "encounter_id": str(payload.encounter_id),
                "thread_id": payload.thread_id,
                "active_document_id": payload.active_document_id,
                "user_message": payload.user_message,
                "workspace_index": payload.workspace_index.model_dump(mode="python"),
                "selected_document_ids": payload.selected_document_ids,
                "trace_metadata": {},
            }
        )
    except CopilotServiceError as error:
        raise HttpError(502, f"Copilot agent unavailable: {error}") from error

    remote_run = response["run"]
    _validate_remote_patch_set_preview(remote_run)
    with transaction.atomic():
        run = CopilotRun.objects.create(
            run_id=remote_run["run_id"],
            thread_id=remote_run["thread_id"],
            doctor=request.user,
            encounter=encounter,
            status=remote_run["status"],
            intent=remote_run.get("intent"),
            requires_human_review=remote_run.get("requires_human_review", False),
        )
        _persist_patch_set_preview(
            run=run,
            remote_run=remote_run,
            user_id=request.user.id,
            encounter_id=payload.encounter_id,
        )
    return _serialize_run(run, remote_run)


@router.get("/copilot/runs/{run_id}", response=CopilotRunOut, auth=django_auth)
def get_copilot_run(request, run_id: str):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    client = CopilotAgentClient()
    try:
        remote_run = client.get_run(run_id)
    except CopilotServiceError as error:
        raise HttpError(502, f"Copilot agent unavailable: {error}") from error

    _validate_remote_patch_set_preview(remote_run)

    run = _sync_run_from_remote(run, remote_run)
    return _serialize_run(run, remote_run)


@router.get("/copilot/runs/{run_id}/patches", response=list[CopilotPatchOut], auth=django_auth)
def list_copilot_patches(request, run_id: str):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    patches = CopilotPatch.objects.filter(run=run, doctor=request.user).select_related(
        "run",
        "patch_set",
    )
    for patch in patches:
        if not getattr(patch, "patch_set_id", None):
            ensure_patch_set_for_legacy_patch(patch)
    return [_serialize_patch(patch) for patch in patches]


@router.get(
    "/copilot/runs/{run_id}/patch-sets",
    response=list[CopilotPatchSetOut],
    auth=django_auth,
)
def list_copilot_patch_sets(request, run_id: str):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    for patch in CopilotPatch.objects.filter(run=run, doctor=request.user, patch_set__isnull=True):
        ensure_patch_set_for_legacy_patch(patch)

    patch_sets = CopilotPatchSet.objects.filter(run=run, doctor=request.user).select_related(
        "run",
        "target_document",
    )
    return [_serialize_patch_set(patch_set) for patch_set in patch_sets]


@router.get(
    "/copilot/patch-sets/{patch_set_id}",
    response=CopilotPatchSetOut,
    auth=django_auth,
)
def get_copilot_patch_set(request, patch_set_id: str):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    return _serialize_patch_set(patch_set)


@router.post(
    "/copilot/patch-sets/{patch_set_id}/accept-patch",
    response=CopilotPatchSetOut,
    auth=django_auth,
)
def accept_copilot_patch(request, patch_set_id: str, payload: CopilotPatchDecisionIn):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    patch = get_object_or_404(
        CopilotPatch,
        patch_id=payload.patch_id,
        patch_set=patch_set,
        doctor=request.user,
    )
    try:
        accept_patch(patch_set=patch_set, patch=patch, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HttpError(409, str(error)) from error
    return _serialize_patch_set(patch_set)


@router.post(
    "/copilot/patch-sets/{patch_set_id}/reject-patch",
    response=CopilotPatchSetOut,
    auth=django_auth,
)
def reject_copilot_patch(request, patch_set_id: str, payload: CopilotPatchDecisionIn):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    patch = get_object_or_404(
        CopilotPatch,
        patch_id=payload.patch_id,
        patch_set=patch_set,
        doctor=request.user,
    )
    try:
        reject_patch(patch_set=patch_set, patch=patch, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HttpError(409, str(error)) from error
    return _serialize_patch_set(patch_set)


@router.post(
    "/copilot/patch-sets/{patch_set_id}/accept-all",
    response=CopilotPatchSetOut,
    auth=django_auth,
)
def accept_all_copilot_patches(request, patch_set_id: str, payload: CopilotPatchSetDecisionIn):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    try:
        accept_all_patches(patch_set=patch_set, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HttpError(409, str(error)) from error
    return _serialize_patch_set(patch_set)


@router.post(
    "/copilot/patch-sets/{patch_set_id}/reject-all",
    response=CopilotPatchSetOut,
    auth=django_auth,
)
def reject_all_copilot_patches(request, patch_set_id: str, payload: CopilotPatchSetDecisionIn):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    try:
        reject_all_patches(patch_set=patch_set, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HttpError(409, str(error)) from error
    return _serialize_patch_set(patch_set)


@router.post(
    "/copilot/patch-sets/{patch_set_id}/apply-accepted",
    response=CopilotRunOut,
    auth=django_auth,
)
def apply_copilot_patch_set(request, patch_set_id: str, payload: CopilotPatchSetDecisionIn):
    patch_set = _get_owned_patch_set(patch_set_id=patch_set_id, user_id=request.user.id)
    run = patch_set.run
    if run.status != "waiting_review":
        raise HttpError(409, "El run no esta esperando revision humana")

    try:
        apply_result = apply_accepted_patch_set(
            patch_set=patch_set,
            document_version=payload.document_version,
            review_comment=payload.comment,
        )
    except CopilotPatchSetConflictError as error:
        raise HttpError(409, str(error)) from error

    client = CopilotAgentClient()
    try:
        remote_run = client.resume_run(
            run.run_id,
            {
                "patch_set_id": patch_set.patch_set_id,
                "review_result": "approve",
                "reviewer_id": str(request.user.id),
                "comment": payload.comment,
                "trace_metadata": {
                    "applied_patch_set_id": apply_result.patch_set_id,
                    "applied_patch_id": apply_result.applied_patch_ids[0]
                    if apply_result.applied_patch_ids
                    else None,
                    "applied_document_id": apply_result.document_id,
                    "applied_content": apply_result.content,
                    "applied_version": apply_result.applied_version,
                    "stale_patch_set_ids": apply_result.stale_patch_set_ids,
                    "stale_patch_ids": apply_result.stale_patch_ids,
                },
            },
        )
    except CopilotServiceError as error:
        raise HttpError(502, f"Copilot agent unavailable: {error}") from error

    run = _sync_run_from_remote(run, remote_run)
    return _serialize_run(run, remote_run)


@router.post("/copilot/runs/{run_id}/review", response=CopilotRunOut, auth=django_auth)
def review_copilot_patch(request, run_id: str, payload: CopilotReviewIn):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    patch = get_object_or_404(
        CopilotPatch,
        patch_id=payload.patch_id,
        run=run,
        doctor=request.user,
    )
    if patch.status != "pending":
        raise HttpError(409, "El patch ya no esta pendiente de revision")
    if run.status != "waiting_review":
        raise HttpError(409, "El run no esta esperando revision humana")

    patch_set = ensure_patch_set_for_legacy_patch(patch)
    if patch_set.patches.count() != 1:
        raise HttpError(
            409,
            "El endpoint legacy /review solo soporta patch sets de un solo cambio.",
        )

    client = CopilotAgentClient()
    resume_trace_metadata: dict[str, Any] = {}

    with transaction.atomic():
        if payload.decision == "approve":
            try:
                accept_patch(
                    patch_set=patch_set,
                    patch=patch,
                    review_comment=payload.comment,
                )
                apply_result = apply_copilot_patch(
                    patch=patch,
                    document_version=payload.document_version,
                    review_comment=payload.comment,
                )
            except CopilotPatchConflictError as error:
                raise HttpError(409, str(error)) from error

            resume_trace_metadata = {
                "applied_patch_set_id": patch_set.patch_set_id,
                "applied_patch_id": apply_result.patch_id,
                "applied_document_id": apply_result.document_id,
                "applied_content": apply_result.content,
                "applied_version": apply_result.applied_version,
                "stale_patch_ids": apply_result.stale_patch_ids,
            }
        else:
            reject_patch(
                patch_set=patch_set,
                patch=patch,
                review_comment=payload.comment,
            )

        try:
            remote_run = client.resume_run(
                run_id,
                {
                    "patch_set_id": patch_set.patch_set_id,
                    "review_result": payload.decision,
                    "reviewer_id": str(request.user.id),
                    "comment": payload.comment,
                    "trace_metadata": resume_trace_metadata,
                },
            )
        except CopilotServiceError as error:
            raise HttpError(502, f"Copilot agent unavailable: {error}") from error

        run = _sync_run_from_remote(run, remote_run)

    return _serialize_run(run, remote_run)


@router.get("/copilot/runs/{run_id}/stream", auth=django_auth)
def stream_copilot_run(request, run_id: str, after_sequence: int = 0):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    client = CopilotAgentClient()

    def event_stream():
        next_after_sequence = after_sequence
        last_ping = time.monotonic()

        while True:
            try:
                response = client.list_run_events(
                    run_id,
                    after_sequence=next_after_sequence,
                )
            except CopilotServiceError as error:
                logger.error("Copilot stream polling failed for run %s: %s", run_id, error)
                run.status = "failed"
                run.save(update_fields=["status", "updated_at"])
                yield (
                    f"event: run_failed\n"
                    f"data: {json.dumps({'run_id': run_id, 'error': str(error)})}\n\n"
                )
                break

            events = response.get("events", [])
            for event in events:
                next_after_sequence = max(next_after_sequence, int(event["sequence"]))
                payload = {
                    "sequence": event["sequence"],
                    "run_id": event["run_id"],
                    "thread_id": event["thread_id"],
                    "created_at": event["created_at"],
                    **event["payload"],
                }
                yield (
                    f"event: {event['event']}\n"
                    f"data: {json.dumps(payload)}\n\n"
                )

            run.status = response.get("status", run.status)
            run.save(update_fields=["status", "updated_at"])

            if response.get("done") or run.status in STREAM_DONE_RUN_STATUSES:
                break

            now = time.monotonic()
            if now - last_ping >= 15:
                yield ": ping\n\n"
                last_ping = now

            time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
