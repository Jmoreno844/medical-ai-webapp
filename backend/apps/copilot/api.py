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

from apps.copilot.models import CopilotPatch, CopilotRun
from apps.copilot.schemas import (
    CopilotMessageIn,
    CopilotPatchOut,
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
from apps.copilot.services.threads import build_thread_id
from apps.documents.models import Document
from apps.encounters.models import Encounter

logger = logging.getLogger(__name__)
router = Router(tags=["copilot"])

STREAM_DONE_RUN_STATUSES = {"completed", "failed", "waiting_review"}


def _serialize_run(run: CopilotRun, remote_run: dict[str, Any] | None = None) -> dict[str, Any]:
    applied_patch_id = None
    applied_document_id = None
    applied_content = None
    applied_version = None
    trace_metadata: dict[str, Any] = {}
    if remote_run:
        trace_metadata = remote_run.get("trace_metadata", {}) or {}
        applied_patch_id = remote_run.get("applied_patch_id")
        applied_document_id = remote_run.get("applied_document_id")
        applied_content = remote_run.get("applied_content")
        applied_version = remote_run.get("applied_version")

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
        "final_response": remote_run.get("final_response") if remote_run else None,
        "applied_patch_id": applied_patch_id,
        "applied_document_id": applied_document_id,
        "applied_content": applied_content,
        "applied_version": applied_version,
        "trace_metadata": trace_metadata if remote_run else {},
    }


def _serialize_patch(patch: CopilotPatch) -> dict[str, Any]:
    return {
        "patch_id": patch.patch_id,
        "run_id": patch.run.run_id,
        "target_document_id": str(patch.target_document_id),
        "base_version": patch.base_version,
        "operation_type": patch.operation_type,
        "anchor": getattr(patch, "anchor", {}) or {},
        "expected_hash": getattr(patch, "expected_hash", None),
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


def _get_owned_encounter(*, encounter_id: int, user_id: int) -> Encounter:
    encounter = get_object_or_404(Encounter, id=encounter_id)
    if encounter.doctor_id != user_id:
        raise HttpError(403, "No tienes permiso para acceder a este encuentro")
    return encounter


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


def _persist_patch_preview(
    *,
    run: CopilotRun,
    remote_run: dict[str, Any],
    user_id: int,
    encounter_id: int,
) -> CopilotPatch | None:
    patch_preview = remote_run.get("patch_preview")
    if not patch_preview:
        return None

    patch_id = str(patch_preview["patch_id"])
    target_document_id = int(patch_preview["target_document_id"])
    target_document = get_object_or_404(
        Document,
        id=target_document_id,
        encounter_id=encounter_id,
        doctor_id=user_id,
    )

    patch_defaults = {
        "encounter_id": encounter_id,
        "doctor_id": user_id,
        "target_document": target_document,
        "base_version": int(patch_preview.get("base_version") or 1),
        "operation_type": str(patch_preview["operation_type"]),
        "anchor": patch_preview.get("anchor") or {},
        "expected_hash": patch_preview.get("expected_hash"),
        "before_preview": patch_preview.get("before_preview"),
        "after_preview": patch_preview.get("after_preview"),
        "document_preview_after": patch_preview.get("document_preview_after"),
        "content_preview": str(
            patch_preview.get("document_preview_after") or patch_preview["content_preview"]
        ),
        "rationale": patch_preview.get("rationale"),
        "source_context_document_ids": [
            str(document_id)
            for document_id in patch_preview.get("source_context_document_ids", [])
        ],
        "target_document_title": patch_preview.get("target_document_title"),
        "target_selection_reason": patch_preview.get("target_selection_reason"),
        "status": "pending",
        "review_comment": None,
    }

    patch, _created = CopilotPatch.objects.update_or_create(
        patch_id=patch_id,
        defaults={
            "run": run,
            **patch_defaults,
        },
    )
    return patch


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
    thread_id = build_thread_id(
        encounter_id=payload.encounter_id,
        user_id=request.user.id,
    )
    client = CopilotAgentClient()

    try:
        response = client.create_run(
            {
                "tenant_id": f"doctor:{request.user.id}",
                "user_id": str(request.user.id),
                "encounter_id": str(payload.encounter_id),
                "thread_id": thread_id,
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
        _persist_patch_preview(
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

    run = _sync_run_from_remote(run, remote_run)
    return _serialize_run(run, remote_run)


@router.get("/copilot/runs/{run_id}/patches", response=list[CopilotPatchOut], auth=django_auth)
def list_copilot_patches(request, run_id: str):
    run = get_object_or_404(CopilotRun, run_id=run_id)
    if run.doctor_id != request.user.id:
        raise HttpError(403, "No tienes permiso para acceder a este run")

    patches = CopilotPatch.objects.filter(run=run, doctor=request.user).select_related("run")
    return [_serialize_patch(patch) for patch in patches]


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

    client = CopilotAgentClient()
    resume_trace_metadata: dict[str, Any] = {}

    with transaction.atomic():
        if payload.decision == "approve":
            try:
                apply_result = apply_copilot_patch(
                    patch=patch,
                    document_version=payload.document_version,
                    review_comment=payload.comment,
                )
            except CopilotPatchConflictError as error:
                raise HttpError(409, str(error)) from error

            resume_trace_metadata = {
                "applied_patch_id": apply_result.patch_id,
                "applied_document_id": apply_result.document_id,
                "applied_content": apply_result.content,
                "applied_version": apply_result.applied_version,
                "stale_patch_ids": apply_result.stale_patch_ids,
            }
        else:
            patch.status = "rejected"
            patch.review_comment = payload.comment
            patch.save(update_fields=["status", "review_comment", "updated_at"])

        try:
            remote_run = client.resume_run(
                run_id,
                {
                    "patch_id": patch.patch_id,
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
