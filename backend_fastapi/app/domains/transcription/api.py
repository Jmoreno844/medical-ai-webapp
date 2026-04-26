from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.service_jwt import issue_transcription_callback_token
from app.db.models import User
from app.db.session import AsyncSessionLocal, get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import get_document_for_doctor, get_encounter_for_doctor
from app.domains.transcription.internal_auth import verify_cloud_tasks_request
from app.domains.transcription.schemas import (
    AudioSectionRegisterRequest,
    AudioSectionRegisterResponse,
    RecordingSessionCreate,
    RecordingSessionFinishResponse,
    RecordingSessionResponse,
    RecordingSessionStatusResponse,
    SectionUploadUrlRequest,
    SectionUploadUrlResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)
from app.domains.transcription.service import (
    SESSION_STATUS_FINISHING,
    build_section_object_name,
    consolidate_recording_session,
    create_recording_session,
    enqueue_legacy_audio_task,
    enqueue_section_task,
    enqueue_session_consolidation_task,
    generate_section_upload_url,
    get_recording_session_for_doctor,
    process_legacy_audio_transcription,
    process_section_transcription,
    register_audio_section,
    serialize_section,
)
from app.integrations.http_json import JsonHttpError, post_json
from app.integrations.transcription_tasks import (
    TranscriptionTaskConfigurationError,
    enqueue_transcription_task,
    should_use_cloud_tasks,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class LegacyTranscriptionTaskPayload(BaseModel):
    document_id: int
    encounter_id: int
    doctor_id: int


async def _process_section_background(section_id: str, settings: Settings) -> None:
    async with AsyncSessionLocal() as db_session:
        try:
            await process_section_transcription(
                db_session,
                section_id=section_id,
                settings=settings,
            )
        except Exception:
            logger.exception("Local background section transcription failed")


async def _consolidate_session_background(session_id: str, settings: Settings) -> None:
    async with AsyncSessionLocal() as db_session:
        try:
            await consolidate_recording_session(
                db_session,
                session_id=session_id,
                settings=settings,
            )
        except Exception:
            logger.exception("Local background transcription consolidation failed")


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
    if not settings.gcs_bucket_name:
        return TranscriptionResponse(success=False, error="GCS_BUCKET_NAME is not configured")
    if not settings.transcription_task_target_url and not settings.transcription_cloud_function_url:
        return TranscriptionResponse(
            success=False,
            error=(
                "TRANSCRIPTION_TASK_TARGET_URL or "
                "TRANSCRIPTION_CLOUD_FUNCTION_URL is not configured"
            ),
        )

    try:
        if settings.transcription_task_target_url:
            if not should_use_cloud_tasks(settings):
                return TranscriptionResponse(
                    success=False,
                    error="Cloud Tasks transcription is not configured",
                )
            task_name = enqueue_legacy_audio_task(
                document_id=document.id,
                encounter_id=encounter.id,
                doctor_id=user.id,
                settings=settings,
            )
            logger.info(
                "FastAPI transcription task queued for document %s with task %s",
                document.id,
                task_name,
            )
            return TranscriptionResponse(
                success=True,
                message="Transcription queued successfully",
            )

        auth_token = issue_transcription_callback_token(
            user_id=user.id,
            document_id=document.id,
            settings=settings,
        )
        cloud_function_payload = {
            "document_id": document.id,
            "audio_uri": f"gs://{settings.gcs_bucket_name}/{encounter.audio_file_name}",
            "auth_token": auth_token,
        }
        if should_use_cloud_tasks(settings):
            task_name = enqueue_transcription_task(
                cloud_function_payload,
                settings=settings,
            )
            logger.info(
                "Legacy Cloud Function transcription task queued for document %s "
                "with task %s",
                document.id,
                task_name,
            )
            return TranscriptionResponse(
                success=True,
                message="Transcription queued successfully",
            )

        await asyncio.to_thread(
            post_json,
            settings.transcription_cloud_function_url,
            cloud_function_payload,
            timeout=30,
        )
        return TranscriptionResponse(
            success=True,
            message="Transcription initiated successfully",
        )
    except TranscriptionTaskConfigurationError as exc:
        logger.error("Cloud Tasks transcription misconfigured: %s", exc)
        return TranscriptionResponse(success=False, error=str(exc))
    except JsonHttpError as exc:
        logger.error("Error calling transcription cloud function: %s", exc)
        return TranscriptionResponse(
            success=False,
            error=f"Failed to initiate transcription: {exc}",
        )


@router.post("/transcription/sessions", response_model=RecordingSessionResponse)
async def create_transcription_recording_session(
    payload: RecordingSessionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecordingSessionResponse:
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SectionUploadUrlResponse:
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
    upload_url = generate_section_upload_url(
        settings=settings,
        gcs_object_name=gcs_object_name,
        content_type=payload.content_type,
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AudioSectionRegisterResponse:
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
    await session.commit()

    if should_use_cloud_tasks(settings):
        try:
            enqueue_section_task(section, settings)
        except Exception as exc:
            logger.error("Failed to enqueue section transcription: %s", exc)
            return AudioSectionRegisterResponse(
                success=False,
                section=serialize_section(section),
                error=str(exc),
            )
    else:
        background_tasks.add_task(_process_section_background, section.section_id, settings)

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
    settings: Settings = Depends(get_settings),
) -> RecordingSessionFinishResponse:
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

    if should_use_cloud_tasks(settings):
        try:
            enqueue_session_consolidation_task(recording_session, settings)
        except Exception as exc:
            logger.error("Failed to enqueue consolidation task: %s", exc)
            return RecordingSessionFinishResponse(
                success=False,
                status=recording_session.status,
                error=str(exc),
            )
    else:
        background_tasks.add_task(
            _consolidate_session_background,
            recording_session.session_id,
            settings,
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


@router.post("/internal/transcription/tasks/sections/{section_id}")
async def run_section_transcription_task(
    section_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    section = await process_section_transcription(
        session,
        section_id=section_id,
        settings=settings,
    )
    if not section:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sección no encontrada")
    return {"success": True}


@router.post("/internal/transcription/tasks/sessions/{session_id}/consolidate")
async def run_session_consolidation_task(
    session_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    recording_session = await consolidate_recording_session(
        session,
        session_id=session_id,
        settings=settings,
    )
    if not recording_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesión no encontrada")
    return {"success": True}


@router.post("/internal/transcription/tasks/legacy-audio")
async def run_legacy_audio_transcription_task(
    payload: LegacyTranscriptionTaskPayload,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    verify_cloud_tasks_request(request, settings)
    success = await process_legacy_audio_transcription(
        session,
        document_id=payload.document_id,
        encounter_id=payload.encounter_id,
        doctor_id=payload.doctor_id,
        settings=settings,
    )
    if not success:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio legacy no encontrado")
    return {"success": True}
