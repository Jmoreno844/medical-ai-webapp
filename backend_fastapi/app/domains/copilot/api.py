from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CopilotPatch, CopilotPatchSet, CopilotRun, Document, Encounter, User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.copilot.client import CopilotAgentClient, CopilotServiceError
from app.domains.copilot.patch_sets import (
    CopilotPatchSetConflictError,
    accept_all_patches,
    accept_patch,
    apply_accepted_patch_set,
    reject_all_patches,
    reject_patch,
)
from app.domains.copilot.patch_sets import persist_patch_set_preview as persist_patch_set_preview_service
from app.domains.copilot.schemas import (
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
from app.domains.copilot.threads import build_thread_id, parse_thread_id, thread_belongs_to_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["copilot"])

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


def _normalized_patch_operation_type(value: str | None) -> str:
    operation_type = str(value or "").strip().lower()
    if operation_type in {"insert_after", "insert_after_span"}:
        return "insert_after"
    if operation_type in {"replace_span", "rewrite_document"}:
        return "replace_span"
    if operation_type in {"insert_before", "delete_span"}:
        return operation_type
    return "replace_span"


async def _get_owned_encounter(
    session: AsyncSession, *, encounter_id: int, user_id: int
) -> Encounter:
    result = await session.execute(select(Encounter).where(Encounter.id == encounter_id))
    encounter = result.scalar_one_or_none()
    if encounter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    if encounter.doctor_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para acceder a este encuentro")
    return encounter


async def _get_owned_run(session: AsyncSession, *, run_id: str, user_id: int) -> CopilotRun:
    result = await session.execute(
        select(CopilotRun)
        .options(selectinload(CopilotRun.patch_sets))
        .where(CopilotRun.run_id == run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run no encontrado")
    if run.doctor_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para acceder a este run")
    return run


async def _get_owned_patch_set(
    session: AsyncSession, *, patch_set_id: str, user_id: int
) -> CopilotPatchSet:
    result = await session.execute(
        select(CopilotPatchSet)
        .options(
            selectinload(CopilotPatchSet.run),
            selectinload(CopilotPatchSet.target_document),
            selectinload(CopilotPatchSet.patches).selectinload(CopilotPatch.run),
            selectinload(CopilotPatchSet.patches).selectinload(CopilotPatch.patch_set),
        )
        .where(CopilotPatchSet.patch_set_id == patch_set_id)
    )
    patch_set = result.scalar_one_or_none()
    if patch_set is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch set no encontrado")
    if patch_set.doctor_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para acceder a este patch set")
    return patch_set


async def _get_patch_for_patch_set(
    session: AsyncSession,
    *,
    patch_set: CopilotPatchSet,
    patch_id: str,
    user_id: int,
) -> CopilotPatch:
    result = await session.execute(
        select(CopilotPatch)
        .options(selectinload(CopilotPatch.run), selectinload(CopilotPatch.patch_set))
        .where(
            CopilotPatch.patch_id == patch_id,
            CopilotPatch.patch_set_id == patch_set.id,
            CopilotPatch.doctor_id == user_id,
        )
    )
    patch = result.scalar_one_or_none()
    if patch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch no encontrado")
    return patch


def _serialize_run(run: CopilotRun, remote_run: dict[str, Any] | None = None) -> CopilotRunOut:
    active_patch_set_id = None
    if run.patch_sets:
        active_patch_set_id = sorted(run.patch_sets, key=lambda item: item.created_at, reverse=True)[0].patch_set_id
    trace_metadata = remote_run.get("trace_metadata", {}) if remote_run else {}
    return CopilotRunOut(
        run_id=run.run_id,
        thread_id=run.thread_id,
        status=remote_run.get("status", run.status) if remote_run else run.status,
        intent=remote_run.get("intent", run.intent) if remote_run else run.intent,
        requires_human_review=(
            remote_run.get("requires_human_review", run.requires_human_review)
            if remote_run
            else run.requires_human_review
        ),
        active_patch_set_id=(remote_run.get("active_patch_set_id") if remote_run else None) or active_patch_set_id,
        final_response=remote_run.get("final_response") if remote_run else None,
        applied_patch_set_id=remote_run.get("applied_patch_set_id") if remote_run else None,
        applied_patch_id=remote_run.get("applied_patch_id") if remote_run else None,
        applied_document_id=remote_run.get("applied_document_id") if remote_run else None,
        applied_content=remote_run.get("applied_content") if remote_run else None,
        applied_version=remote_run.get("applied_version") if remote_run else None,
        trace_metadata=trace_metadata or {},
    )


def _serialize_patch(patch: CopilotPatch) -> CopilotPatchOut:
    normalized_operation_type = _normalized_patch_operation_type(patch.patch_type or patch.operation_type)
    return CopilotPatchOut(
        patch_id=patch.patch_id,
        patch_set_id=patch.patch_set.patch_set_id if patch.patch_set else None,
        run_id=patch.run.run_id,
        target_document_id=str(patch.target_document_id),
        base_version=patch.base_version,
        order_index=patch.order_index,
        patch_type=patch.patch_type,  # type: ignore[arg-type]
        operation_type=patch.operation_type,  # type: ignore[arg-type]
        normalized_operation_type=normalized_operation_type,  # type: ignore[arg-type]
        anchor=patch.anchor or {},
        expected_hash=patch.expected_hash,
        replacement_text=patch.replacement_text,
        inserted_text=patch.inserted_text,
        old_text=patch.old_text,
        new_text=patch.new_text,
        resolved_start=patch.resolved_start,
        resolved_end=patch.resolved_end,
        confidence=patch.confidence,
        conflict_reason=patch.conflict_reason,
        document_preview_after=patch.document_preview_after,
        content_preview=patch.content_preview,
        rationale=patch.rationale,
        source_context_document_ids=patch.source_context_document_ids or [],
        target_document_title=patch.target_document_title,
        target_selection_reason=patch.target_selection_reason,
        status=patch.status,  # type: ignore[arg-type]
        review_comment=patch.review_comment,
        section=patch.section,
        created_at=patch.created_at,
        updated_at=patch.updated_at,
    )


def _serialize_patch_set(patch_set: CopilotPatchSet) -> CopilotPatchSetOut:
    patches = sorted(patch_set.patches, key=lambda item: (item.order_index, item.created_at))
    return CopilotPatchSetOut(
        patch_set_id=patch_set.patch_set_id,
        run_id=patch_set.run.run_id,
        target_document_id=str(patch_set.target_document_id),
        base_version=patch_set.base_version,
        base_hash=patch_set.base_hash,
        rationale=patch_set.rationale,
        source_context_document_ids=patch_set.source_context_document_ids or [],
        target_document_title=patch_set.target_document_title,
        target_selection_reason=patch_set.target_selection_reason,
        document_preview_after=patch_set.document_preview_after,
        status=patch_set.status,  # type: ignore[arg-type]
        review_comment=patch_set.review_comment,
        patches=[_serialize_patch(patch) for patch in patches],
        edit_scope=patch_set.edit_scope,
        clinical_impact_level=patch_set.clinical_impact_level,
        affected_sections=patch_set.affected_sections or [],
        created_at=patch_set.created_at,
        updated_at=patch_set.updated_at,
    )


def _sync_run_from_remote(run: CopilotRun, remote_run: dict[str, Any]) -> CopilotRun:
    run.status = remote_run.get("status", run.status)
    run.intent = remote_run.get("intent", run.intent)
    run.requires_human_review = remote_run.get("requires_human_review", run.requires_human_review)
    return run


def _normalize_legacy_patch_set_preview(remote_run: dict[str, Any]) -> dict[str, Any] | None:
    patch_preview = remote_run.get("patch_preview")
    if not patch_preview:
        return None
    return {
        "patch_set_id": remote_run.get("active_patch_set_id") or f"legacy-{patch_preview['patch_id']}",
        "target_document_id": patch_preview["target_document_id"],
        "target_document_title": patch_preview.get("target_document_title"),
        "target_selection_reason": patch_preview.get("target_selection_reason"),
        "base_version": patch_preview.get("base_version") or 1,
        "base_hash": patch_preview.get("base_hash") or patch_preview.get("expected_hash") or "",
        "rationale": patch_preview.get("rationale"),
        "source_context_document_ids": patch_preview.get("source_context_document_ids", []),
        "document_preview_after": patch_preview.get("document_preview_after") or patch_preview.get("content_preview"),
        "patches": [
            {
                "patch_id": patch_preview["patch_id"],
                "patch_type": patch_preview.get("patch_type") or patch_preview.get("operation_type"),
                "operation_type": patch_preview.get("operation_type"),
                "order_index": patch_preview.get("order_index") or 0,
                "anchor": patch_preview.get("anchor") or {},
                "expected_hash": patch_preview.get("expected_hash"),
                "replacement_text": patch_preview.get("replacement_text"),
                "inserted_text": patch_preview.get("inserted_text"),
                "old_text": patch_preview.get("old_text"),
                "new_text": patch_preview.get("new_text"),
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
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Copilot agent devolvio waiting_review sin un patch_set_preview valido.",
            )
        return None
    missing_fields = [field for field in PATCH_SET_PREVIEW_REQUIRED_FIELDS if not patch_set_preview.get(field)]
    if missing_fields:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Copilot agent devolvio un patch_set_preview incompleto: " + ", ".join(missing_fields),
        )
    if remote_run.get("status") != "waiting_review" or not remote_run.get("requires_human_review"):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Copilot agent devolvio un patch set de edicion sin dejar el run en waiting_review.",
        )
    return patch_set_preview


async def _persist_patch_set_preview(
    session: AsyncSession,
    *,
    run: CopilotRun,
    remote_run: dict[str, Any],
    user_id: int,
    encounter_id: int,
) -> CopilotPatchSet | None:
    patch_set_preview = _validate_remote_patch_set_preview(remote_run)
    if not patch_set_preview:
        return None
    result = await session.execute(
        select(Document).where(
            Document.id == int(patch_set_preview["target_document_id"]),
            Document.encounter_id == encounter_id,
            Document.doctor_id == user_id,
        )
    )
    target_document = result.scalar_one_or_none()
    if target_document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento destino no encontrado")
    try:
        return await persist_patch_set_preview_service(
            session,
            run=run,
            target_document=target_document,
            patch_set_preview=patch_set_preview,
            user_id=user_id,
            encounter_id=encounter_id,
        )
    except CopilotPatchSetConflictError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


async def _call_agent(method, *args, **kwargs) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(method, *args, **kwargs)
    except CopilotServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Copilot agent unavailable: {error}") from error


@router.post("/sessions", response_model=CopilotSessionOut)
async def create_copilot_session(
    payload: CopilotSessionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotSessionOut:
    await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=user.id)
    return CopilotSessionOut(
        thread_id=build_thread_id(encounter_id=payload.encounter_id, user_id=user.id),
        capability="read_only",
    )


@router.post("/messages", response_model=CopilotRunOut)
async def create_copilot_message(
    payload: CopilotMessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotRunOut:
    encounter = await _get_owned_encounter(session, encounter_id=payload.encounter_id, user_id=user.id)
    if parse_thread_id(payload.thread_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "thread_id invalido")
    if not thread_belongs_to_scope(thread_id=payload.thread_id, encounter_id=payload.encounter_id, user_id=user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para usar este thread")

    response = await _call_agent(
        CopilotAgentClient().create_run,
        {
            "tenant_id": f"doctor:{user.id}",
            "user_id": str(user.id),
            "encounter_id": str(payload.encounter_id),
            "thread_id": payload.thread_id,
            "active_document_id": payload.active_document_id,
            "user_message": payload.user_message,
            "workspace_index": payload.workspace_index.model_dump(mode="python"),
            "selected_document_ids": payload.selected_document_ids,
            "trace_metadata": {},
        },
    )
    remote_run = response["run"]
    _validate_remote_patch_set_preview(remote_run)
    now = datetime.now(UTC)
    run = CopilotRun(
        run_id=remote_run["run_id"],
        thread_id=remote_run["thread_id"],
        doctor_id=user.id,
        encounter=encounter,
        status=remote_run["status"],
        intent=remote_run.get("intent"),
        requires_human_review=remote_run.get("requires_human_review", False),
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.flush()
    await _persist_patch_set_preview(
        session,
        run=run,
        remote_run=remote_run,
        user_id=user.id,
        encounter_id=payload.encounter_id,
    )
    await session.commit()
    await session.refresh(run, attribute_names=["patch_sets"])
    return _serialize_run(run, remote_run)


@router.get("/runs/{run_id}", response_model=CopilotRunOut)
async def get_copilot_run(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotRunOut:
    run = await _get_owned_run(session, run_id=run_id, user_id=user.id)
    remote_run = await _call_agent(CopilotAgentClient().get_run, run_id)
    _validate_remote_patch_set_preview(remote_run)
    _sync_run_from_remote(run, remote_run)
    # With the async agent path the run was created with status="running" and no
    # patch set. When the background graph finishes and review_required arrives
    # via SSE, the frontend calls syncRunStatus -> getCopilotRun. This is the
    # first time FastAPI sees the completed patch_set_preview, so we must persist
    # it here so the subsequent listCopilotPatchSets call finds it in the DB.
    await _persist_patch_set_preview(
        session,
        run=run,
        remote_run=remote_run,
        user_id=user.id,
        encounter_id=run.encounter_id,
    )
    await session.commit()
    await session.refresh(run, attribute_names=["patch_sets"])
    return _serialize_run(run, remote_run)


@router.get("/runs/{run_id}/patches", response_model=list[CopilotPatchOut])
async def list_copilot_patches(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CopilotPatchOut]:
    run = await _get_owned_run(session, run_id=run_id, user_id=user.id)
    result = await session.execute(
        select(CopilotPatch)
        .options(selectinload(CopilotPatch.run), selectinload(CopilotPatch.patch_set))
        .where(CopilotPatch.run_id == run.id, CopilotPatch.doctor_id == user.id)
    )
    return [_serialize_patch(patch) for patch in result.scalars().all()]


@router.get("/runs/{run_id}/patch-sets", response_model=list[CopilotPatchSetOut])
async def list_copilot_patch_sets(
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CopilotPatchSetOut]:
    run = await _get_owned_run(session, run_id=run_id, user_id=user.id)
    result = await session.execute(
        select(CopilotPatchSet)
        .options(
            selectinload(CopilotPatchSet.run),
            selectinload(CopilotPatchSet.patches).selectinload(CopilotPatch.run),
            selectinload(CopilotPatchSet.patches).selectinload(CopilotPatch.patch_set),
        )
        .where(CopilotPatchSet.run_id == run.id, CopilotPatchSet.doctor_id == user.id)
        .order_by(CopilotPatchSet.created_at.desc(), CopilotPatchSet.id.desc())
    )
    return [_serialize_patch_set(patch_set) for patch_set in result.scalars().all()]


@router.get("/patch-sets/{patch_set_id}", response_model=CopilotPatchSetOut)
async def get_copilot_patch_set(
    patch_set_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotPatchSetOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return _serialize_patch_set(patch_set)


@router.post("/patch-sets/{patch_set_id}/accept-patch", response_model=CopilotPatchSetOut)
async def accept_copilot_patch(
    patch_set_id: str,
    payload: CopilotPatchDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotPatchSetOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    patch = await _get_patch_for_patch_set(session, patch_set=patch_set, patch_id=payload.patch_id, user_id=user.id)
    try:
        await accept_patch(session, patch_set=patch_set, patch=patch, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return _serialize_patch_set(patch_set)


@router.post("/patch-sets/{patch_set_id}/reject-patch", response_model=CopilotPatchSetOut)
async def reject_copilot_patch(
    patch_set_id: str,
    payload: CopilotPatchDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotPatchSetOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    patch = await _get_patch_for_patch_set(session, patch_set=patch_set, patch_id=payload.patch_id, user_id=user.id)
    try:
        await reject_patch(session, patch_set=patch_set, patch=patch, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return _serialize_patch_set(patch_set)


@router.post("/patch-sets/{patch_set_id}/accept-all", response_model=CopilotPatchSetOut)
async def accept_all_copilot_patches(
    patch_set_id: str,
    payload: CopilotPatchSetDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotPatchSetOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    try:
        await accept_all_patches(session, patch_set=patch_set, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return _serialize_patch_set(patch_set)


@router.post("/patch-sets/{patch_set_id}/reject-all", response_model=CopilotPatchSetOut)
async def reject_all_copilot_patches(
    patch_set_id: str,
    payload: CopilotPatchSetDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotPatchSetOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    try:
        await reject_all_patches(session, patch_set=patch_set, review_comment=payload.comment)
    except CopilotPatchSetConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    await session.commit()
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return _serialize_patch_set(patch_set)


async def _finalize_patch_set_review(
    session: AsyncSession,
    *,
    user: User,
    patch_set: CopilotPatchSet,
    payload: CopilotPatchSetDecisionIn,
    allow_reject_when_no_accepted: bool,
) -> CopilotRunOut:
    run = patch_set.run
    if run.status != "waiting_review":
        return _serialize_run(run)
    if any(patch.status == "pending" for patch in patch_set.patches):
        raise HTTPException(status.HTTP_409_CONFLICT, "Aun hay patches pendientes de decision dentro del patch set")
    accepted_exists = any(patch.status == "accepted" for patch in patch_set.patches)
    if accepted_exists:
        try:
            apply_result = await apply_accepted_patch_set(
                session,
                patch_set=patch_set,
                document_version=payload.document_version,
                review_comment=payload.comment,
            )
        except CopilotPatchSetConflictError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        resume_payload = {
            "patch_set_id": patch_set.patch_set_id,
            "review_result": "approve",
            "reviewer_id": str(user.id),
            "comment": payload.comment,
            "trace_metadata": {
                "applied_patch_set_id": apply_result.patch_set_id,
                "applied_patch_id": apply_result.applied_patch_ids[0] if apply_result.applied_patch_ids else None,
                "applied_document_id": apply_result.document_id,
                "applied_content": apply_result.content,
                "applied_version": apply_result.applied_version,
                "stale_patch_set_ids": apply_result.stale_patch_set_ids,
                "stale_patch_ids": apply_result.stale_patch_ids,
            },
        }
    else:
        if not allow_reject_when_no_accepted:
            raise HTTPException(status.HTTP_409_CONFLICT, "No hay patches aceptados para aplicar en este patch set")
        resume_payload = {
            "patch_set_id": patch_set.patch_set_id,
            "review_result": "reject",
            "reviewer_id": str(user.id),
            "comment": payload.comment,
            "trace_metadata": {},
        }
    try:
        remote_run = await asyncio.to_thread(CopilotAgentClient().resume_run, run.run_id, resume_payload)
    except CopilotServiceError as error:
        # 409 means the agent already completed this run (race condition: the
        # agent finished processing the review decision via SSE before our
        # resume HTTP call landed). apply_accepted_patch_set already persisted
        # the content, so we can build a synthetic completed response and avoid
        # surfacing a misleading 502 to the doctor.
        if error.status_code == 409 and accepted_exists:
            remote_run = {
                "status": "completed",
                "requires_human_review": False,
                "final_response": None,
                "applied_document_id": apply_result.document_id,
                "applied_content": apply_result.content,
                "applied_version": apply_result.applied_version,
            }
        elif error.status_code == 409:
            remote_run = {"status": "completed", "requires_human_review": False, "final_response": None}
        else:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Copilot agent unavailable: {error}") from error
    _sync_run_from_remote(run, remote_run)
    await session.commit()
    return _serialize_run(run, remote_run)


@router.post("/patch-sets/{patch_set_id}/apply-accepted", response_model=CopilotRunOut)
async def apply_copilot_patch_set(
    patch_set_id: str,
    payload: CopilotPatchSetDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotRunOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return await _finalize_patch_set_review(
        session,
        user=user,
        patch_set=patch_set,
        payload=payload,
        allow_reject_when_no_accepted=False,
    )


@router.post("/patch-sets/{patch_set_id}/finalize-review", response_model=CopilotRunOut)
async def finalize_copilot_patch_set_review(
    patch_set_id: str,
    payload: CopilotPatchSetDecisionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotRunOut:
    patch_set = await _get_owned_patch_set(session, patch_set_id=patch_set_id, user_id=user.id)
    return await _finalize_patch_set_review(
        session,
        user=user,
        patch_set=patch_set,
        payload=payload,
        allow_reject_when_no_accepted=True,
    )


@router.post("/runs/{run_id}/review", response_model=CopilotRunOut)
async def review_copilot_patch(
    run_id: str,
    payload: CopilotReviewIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CopilotRunOut:
    run = await _get_owned_run(session, run_id=run_id, user_id=user.id)
    result = await session.execute(
        select(CopilotPatchSet)
        .options(selectinload(CopilotPatchSet.run), selectinload(CopilotPatchSet.patches))
        .join(CopilotPatch, CopilotPatch.patch_set_id == CopilotPatchSet.id)
        .where(CopilotPatch.patch_id == payload.patch_id, CopilotPatch.run_id == run.id)
    )
    patch_set = result.scalar_one_or_none()
    if patch_set is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch no encontrado")
    patch = next((item for item in patch_set.patches if item.patch_id == payload.patch_id), None)
    if patch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch no encontrado")
    if payload.decision == "approve":
        await accept_patch(session, patch_set=patch_set, patch=patch, review_comment=payload.comment)
    else:
        await reject_patch(session, patch_set=patch_set, patch=patch, review_comment=payload.comment)
    return await _finalize_patch_set_review(
        session,
        user=user,
        patch_set=patch_set,
        payload=CopilotPatchSetDecisionIn(comment=payload.comment, document_version=payload.document_version),
        allow_reject_when_no_accepted=True,
    )


@router.get("/runs/{run_id}/stream")
async def stream_copilot_run(
    run_id: str,
    after_sequence: int = Query(default=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    await _get_owned_run(session, run_id=run_id, user_id=user.id)

    async def event_stream() -> AsyncIterator[str]:
        next_after_sequence = after_sequence
        last_ping = time.monotonic()
        while True:
            try:
                response = await asyncio.to_thread(
                    CopilotAgentClient().list_run_events,
                    run_id,
                    after_sequence=next_after_sequence,
                )
            except CopilotServiceError as error:
                logger.error("Copilot stream polling failed for run %s: %s", run_id, error)
                yield f"event: run_failed\ndata: {json.dumps({'run_id': run_id, 'error': str(error)})}\n\n"
                break

            for event in response.get("events", []):
                next_after_sequence = max(next_after_sequence, int(event["sequence"]))
                payload = {
                    "sequence": event["sequence"],
                    "run_id": event["run_id"],
                    "thread_id": event["thread_id"],
                    "created_at": event["created_at"],
                    **event["payload"],
                }
                yield f"event: {event['event']}\ndata: {json.dumps(payload)}\n\n"

            if response.get("done") or response.get("status") in STREAM_DONE_RUN_STATUSES:
                break
            if time.monotonic() - last_ping >= 15:
                yield ": ping\n\n"
                last_ping = time.monotonic()
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
