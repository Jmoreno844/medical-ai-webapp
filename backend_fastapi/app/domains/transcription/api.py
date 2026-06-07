from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.observability import bind_log_context, log_event
from app.db.models import User
from app.db.session import AsyncSessionLocal, get_db_session
from app.domains.audit.service import AuditActor, actor_from_user, record_audit_event
from app.domains.auth.access import require_clinical_access
from app.domains.auth.service import get_current_user
from app.domains.documents.service import get_document_for_doctor, get_encounter_for_doctor
from app.domains.transcription.schemas import (
    AudioSectionRegisterRequest,
    AudioSectionRegisterResponse,
    RecordingSessionCreate,
    RecordingSessionFinishResponse,
    RecordingSessionResponse,
    RecordingSessionRetryResponse,
    RecordingSessionStatusResponse,
    SectionResultRequest,
    SectionUploadUrlRequest,
    SectionUploadUrlResponse,
    SectionWorkItemResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)
from app.domains.transcription.service import (
    SESSION_STATUS_FINISHING,
    apply_section_worker_result,
    build_section_object_name,
    consolidate_recording_session,
    create_recording_session,
    enqueue_section_task,
    generate_section_upload_url,
    get_canonical_recording_session_for_document,
    get_recording_session_for_doctor,
    get_section_work_item,
    is_recording_session_ready_for_consolidation,
    publish_transcription_error,
    reconcile_stuck_transcription_sections,
    register_audio_section,
    retry_failed_transcription_session,
    serialize_section,
    transcription_user_message,
)
from app.domains.transcription.worker_auth import verify_transcription_worker_request
from app.integrations.http_json import post_json_async
from app.integrations.storage import upload_url_user_error_message
from app.integrations.transcription_tasks import (
    should_use_cloud_tasks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _consolidate_session_background(session_id: str) -> None:
    async with AsyncSessionLocal() as db_session:
        try:
            await consolidate_recording_session(
                db_session,
                session_id=session_id,
            )
        except Exception:
            logger.exception("Local background transcription consolidation failed")


async def _post_worker_task_background(path: str, settings: Settings) -> None:
    if not settings.transcription_worker_base_url:
        return
    url = f"{settings.transcription_worker_base_url.rstrip('/')}{path}"
    try:
        with bind_log_context(section_id=path.rsplit("/", 1)[-1]):
            await post_json_async(url, {}, timeout=5)
    except Exception:
        log_event(
            logger,
            logging.ERROR,
            "Local transcription worker task dispatch failed",
            event="transcription_worker_dispatch_failed",
            section_id=path.rsplit("/", 1)[-1],
        )


@router.post("/transcription/start", response_model=TranscriptionResponse)
async def start_transcription(
    payload: TranscriptionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse:
    encounter = await get_encounter_for_doctor(
        session,
        encounter_id=payload.encounter_id,
        doctor_id=user.id,
    )
    if not encounter:
        return TranscriptionResponse(
            success=False,
            error="Not authorized for this encounter",
        )
    if not encounter.audio_file_name:
        return TranscriptionResponse(
            success=False,
            error="No audio file associated with this encounter",
        )
    if encounter.audio_expires_at:
        now = datetime.now(encounter.audio_expires_at.tzinfo)
        if encounter.audio_expires_at <= now:
            return TranscriptionResponse(success=False, error="Audio file has expired")

    document = await get_document_for_doctor(
        session,
        document_id=payload.document_id,
        doctor_id=user.id,
    )
    if not document or document.encounter_id != encounter.id:
        return TranscriptionResponse(
            success=False,
            error="No tienes permiso para acceder a este documento",
        )
    return TranscriptionResponse(
        success=False,
        error=(
            "Legacy full-audio transcription is no longer supported by FastAPI. "
            "Use segmented recording sessions so transcription runs in the worker."
        ),
    )


@router.post("/transcription/sessions", response_model=RecordingSessionResponse)
async def create_transcription_recording_session(
    payload: RecordingSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecordingSessionResponse:
    require_clinical_access(user)
    encounter = await get_encounter_for_doctor(
        session,
        encounter_id=payload.encounter_id,
        doctor_id=user.id,
    )
    document = await get_document_for_doctor(
        session,
        document_id=payload.document_id,
        doctor_id=user.id,
    )
    if not encounter or not document or document.encounter_id != encounter.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro o documento no encontrado")

    recording_session = await create_recording_session(
        session,
        encounter=encounter,
        document=document,
        doctor_id=user.id,
    )
    await record_audit_event(
        session,
        action="audio.transcription_started",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=encounter.id,
        document_id=document.id,
        resource_type="recording_session",
        resource_id=recording_session.session_id,
    )
    await session.commit()
    return RecordingSessionResponse(
        success=True,
        session_id=recording_session.session_id,
        status=recording_session.status,
    )


@router.post(
    "/transcription/sessions/{session_id}/sections/upload-url",
    response_model=SectionUploadUrlResponse,
)
async def create_section_upload_url(
    session_id: str,
    payload: SectionUploadUrlRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SectionUploadUrlResponse:
    require_clinical_access(user)
    if not settings.gcs_bucket_name:
        return SectionUploadUrlResponse(success=False, error="GCS_BUCKET_NAME no configurado")
    recording_session = await get_recording_session_for_doctor(
        session,
        session_id=session_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    gcs_object_name = build_section_object_name(
        encounter_id=recording_session.encounter_id,
        session_id=recording_session.session_id,
        client_section_id=payload.client_section_id,
        section_index=payload.section_index,
    )
    try:
        upload_url = generate_section_upload_url(
            settings=settings,
            gcs_object_name=gcs_object_name,
            content_type=payload.content_type,
        )
    except Exception as exc:
        logger.exception(
            "Failed to generate section upload URL for session_id=%s section_index=%s",
            session_id,
            payload.section_index,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=SectionUploadUrlResponse(
                success=False,
                error=upload_url_user_error_message(exc),
            ).model_dump(),
        )
    return SectionUploadUrlResponse(
        success=True,
        upload_url=upload_url,
        gcs_object_name=gcs_object_name,
    )


@router.post(
    "/transcription/sessions/{session_id}/sections",
    response_model=AudioSectionRegisterResponse,
)
async def register_transcription_section(
    session_id: str,
    payload: AudioSectionRegisterRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AudioSectionRegisterResponse:
    require_clinical_access(user)
    recording_session = await get_recording_session_for_doctor(
        session,
        session_id=session_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    section = await register_audio_section(
        session,
        recording_session=recording_session,
        client_section_id=payload.client_section_id,
        section_index=payload.section_index,
        start_time_ms=payload.start_time_ms,
        end_time_ms=payload.end_time_ms,
        overlap_ms=payload.overlap_ms,
        gcs_object_name=payload.gcs_object_name,
        content_type=payload.content_type,
        byte_size=payload.byte_size,
    )
    await record_audit_event(
        session,
        action="audio.section_registered",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        resource_type="audio_section",
        resource_id=section.section_id,
    )
    await session.commit()

    if should_use_cloud_tasks(settings):
        try:
            enqueue_section_task(section, settings)
        except Exception as exc:
            logger.error("Failed to enqueue section transcription: %s", exc)
            error_code = "section_dispatch_failed"
            await publish_transcription_error(
                recording_session.document_id,
                error_code,
                error=transcription_user_message(error_code),
            )
            return AudioSectionRegisterResponse(
                success=False,
                section=serialize_section(section),
                error=transcription_user_message(error_code),
            )
    elif settings.transcription_worker_base_url:
        background_tasks.add_task(
            _post_worker_task_background,
            f"{settings.api_v1_prefix}/internal/transcription/tasks/sections/{section.section_id}",
            settings,
        )
    else:
        return AudioSectionRegisterResponse(
            success=False,
            section=serialize_section(section),
            error="TRANSCRIPTION_WORKER_BASE_URL is required for local transcription",
        )

    return AudioSectionRegisterResponse(success=True, section=serialize_section(section))


@router.post(
    "/transcription/sessions/{session_id}/finish",
    response_model=RecordingSessionFinishResponse,
)
async def finish_transcription_recording_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecordingSessionFinishResponse:
    require_clinical_access(user)
    recording_session = await get_recording_session_for_doctor(
        session,
        session_id=session_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    if not recording_session.finished_at:
        recording_session.finished_at = datetime.now(timezone.utc)
    recording_session.status = SESSION_STATUS_FINISHING
    await session.commit()

    if is_recording_session_ready_for_consolidation(recording_session):
        background_tasks.add_task(
            _consolidate_session_background,
            recording_session.session_id,
        )

    return RecordingSessionFinishResponse(success=True, status=recording_session.status)


@router.get(
    "/transcription/sessions/{session_id}",
    response_model=RecordingSessionStatusResponse,
)
async def get_transcription_recording_session_status(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecordingSessionStatusResponse:
    recording_session = await get_recording_session_for_doctor(
        session,
        session_id=session_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")
    await reconcile_stuck_transcription_sections(session, recording_session)
    return RecordingSessionStatusResponse(
        success=True,
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        status=recording_session.status,
        started_at=recording_session.started_at,
        finished_at=recording_session.finished_at,
        finalized_at=recording_session.finalized_at,
        consolidated_transcript=recording_session.consolidated_transcript,
        error_code=recording_session.error_code,
        sections=[serialize_section(section) for section in recording_session.sections],
    )


@router.get(
    "/transcription/documents/{document_id}/session",
    response_model=RecordingSessionStatusResponse,
)
async def get_transcription_document_recording_session_status(
    document_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecordingSessionStatusResponse:
    document = await get_document_for_doctor(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not document:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")

    recording_session = await get_canonical_recording_session_for_document(
        session,
        document_id=document_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    await reconcile_stuck_transcription_sections(session, recording_session)
    return RecordingSessionStatusResponse(
        success=True,
        session_id=recording_session.session_id,
        encounter_id=recording_session.encounter_id,
        document_id=recording_session.document_id,
        status=recording_session.status,
        started_at=recording_session.started_at,
        finished_at=recording_session.finished_at,
        finalized_at=recording_session.finalized_at,
        consolidated_transcript=recording_session.consolidated_transcript,
        error_code=recording_session.error_code,
        sections=[serialize_section(section) for section in recording_session.sections],
    )


@router.post(
    "/transcription/sessions/{session_id}/retry",
    response_model=RecordingSessionRetryResponse,
)
async def retry_transcription_recording_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> RecordingSessionRetryResponse:
    require_clinical_access(user)
    recording_session = await get_recording_session_for_doctor(
        session,
        session_id=session_id,
        doctor_id=user.id,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")

    success, error_code, local_sections = await retry_failed_transcription_session(
        session,
        recording_session,
        settings=settings,
    )
    if not success:
        return RecordingSessionRetryResponse(
            success=False,
            status=recording_session.status,
            error=transcription_user_message(error_code),
            error_code=error_code,
        )

    for section in local_sections:
        background_tasks.add_task(
            _post_worker_task_background,
            f"{settings.api_v1_prefix}/internal/transcription/tasks/sections/{section.section_id}",
            settings,
        )

    return RecordingSessionRetryResponse(
        success=True,
        status=recording_session.status,
    )


@router.get(
    "/internal/transcription/work-items/sections/{section_id}",
    response_model=SectionWorkItemResponse,
)
async def get_worker_section_work_item(
    section_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SectionWorkItemResponse:
    verify_transcription_worker_request(request, settings)
    work_item = await get_section_work_item(
        session,
        section_id=section_id,
        settings=settings,
    )
    if not work_item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sección no encontrada")
    return work_item


@router.post("/internal/transcription/results/sections/{section_id}")
async def receive_worker_section_result(
    section_id: str,
    payload: SectionResultRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    worker_principal = verify_transcription_worker_request(request, settings)
    section = await apply_section_worker_result(
        session,
        section_id=section_id,
        status=payload.status,
        transcript=payload.transcript,
        error_code=payload.error_code,
        settings=settings,
    )
    if not section:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sección no encontrada")
    await record_audit_event(
        session,
        action="service.audio_processed",
        result="success" if payload.status == "completed" else "failure",
        request=request,
        actor=AuditActor(None, "service", None, None),
        encounter_id=section.recording_session.encounter_id,
        document_id=section.recording_session.document_id,
        resource_type="audio_section",
        resource_id=section.section_id,
        service_name="transcription_worker",
        service_account=str(worker_principal.get("email")) if worker_principal else None,
        error_code=payload.error_code,
    )
    await record_audit_event(
        session,
        action=(
            "audio.transcription_completed"
            if payload.status == "completed"
            else "audio.transcription_failed"
        ),
        result="success" if payload.status == "completed" else "failure",
        request=request,
        actor=AuditActor(None, "service", None, None),
        encounter_id=section.recording_session.encounter_id,
        document_id=section.recording_session.document_id,
        resource_type="audio_section",
        resource_id=section.section_id,
        service_name="transcription_worker",
        service_account=str(worker_principal.get("email")) if worker_principal else None,
        error_code=payload.error_code,
    )
    await session.commit()
    logger.info(
        "transcription_worker_section_result section_id=%s status=%s vad_decision=%s",
        section_id,
        payload.status,
        payload.vad_decision,
    )
    return {"success": True}
