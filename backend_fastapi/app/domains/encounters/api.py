from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.domains.audit.service import actor_from_user, record_audit_event
from app.db.models import (
    CopilotPatch,
    CopilotPatchSet,
    CopilotRun,
    Document,
    Encounter,
    Patient,
    PatientDoctor,
    TranscriptionAudioSection,
    TranscriptionRecordingSession,
    User,
)
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import new_empty_document
from app.domains.documents.content import set_document_content_fields
from app.domains.transcription.service import (
    get_canonical_recording_session_for_document,
    reset_recording_session,
)
from app.integrations.storage import (
    generate_v4_upload_signed_url,
    get_storage_client,
    upload_url_user_error_message,
)
from app.core.schemas import SuccessResponse
from app.domains.encounters.schemas import (
    AudioExistsResponse,
    AudioUploadRequest,
    AudioUploadResponse,
    EmptyEncounterResponse,
    EmptyPayload,
    EncounterDetail,
    EncounterListItem,
    EncounterUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialize_encounter(encounter: Encounter) -> EncounterDetail:
    return EncounterDetail(
        id=encounter.id,
        doctor_id=encounter.doctor_id,
        patient_id=encounter.patient_id,
        patient_connected=encounter.patient_connected,
        encounter_name=encounter.encounter_name,
        occurred_at=encounter.occurred_at,
        has_been_transcribed=encounter.has_been_transcribed,
    )


async def _get_encounter_or_404(
    session: AsyncSession,
    *,
    encounter_id: int,
    doctor_id: int,
) -> Encounter:
    result = await session.execute(
        select(Encounter).where(
            Encounter.id == encounter_id,
            Encounter.doctor_id == doctor_id,
        )
    )
    encounter = result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encuentro no encontrado")
    return encounter


async def _get_sectioned_audio_summary(
    session: AsyncSession,
    *,
    encounter_id: int,
    doctor_id: int,
) -> tuple[bool, int]:
    result = await session.execute(
        select(
            func.count(TranscriptionAudioSection.id),
            func.max(TranscriptionAudioSection.end_time_ms),
        )
        .select_from(TranscriptionRecordingSession)
        .join(
            TranscriptionAudioSection,
            TranscriptionAudioSection.recording_session_id
            == TranscriptionRecordingSession.id,
        )
        .where(
            TranscriptionRecordingSession.encounter_id == encounter_id,
            TranscriptionRecordingSession.doctor_id == doctor_id,
        )
    )
    section_count, max_end_time_ms = result.one()
    if not section_count:
        return False, 0

    duration_seconds = int(((max_end_time_ms or 0) + 999) // 1000)
    return True, duration_seconds


def _recording_session_ids_for_encounter(*, encounter_id: int, doctor_id: int):
    return select(TranscriptionRecordingSession.id).where(
        TranscriptionRecordingSession.encounter_id == encounter_id,
        TranscriptionRecordingSession.doctor_id == doctor_id,
    )


async def _delete_encounter_dependents(
    session: AsyncSession,
    *,
    encounter_id: int,
    doctor_id: int,
) -> None:
    recording_session_ids = _recording_session_ids_for_encounter(
        encounter_id=encounter_id,
        doctor_id=doctor_id,
    )
    await session.execute(
        delete(TranscriptionAudioSection).where(
            TranscriptionAudioSection.recording_session_id.in_(recording_session_ids)
        )
    )
    await session.execute(
        delete(TranscriptionRecordingSession).where(
            TranscriptionRecordingSession.encounter_id == encounter_id,
            TranscriptionRecordingSession.doctor_id == doctor_id,
        )
    )
    await session.execute(
        delete(CopilotPatch).where(
            CopilotPatch.encounter_id == encounter_id,
            CopilotPatch.doctor_id == doctor_id,
        )
    )
    await session.execute(
        delete(CopilotPatchSet).where(
            CopilotPatchSet.encounter_id == encounter_id,
            CopilotPatchSet.doctor_id == doctor_id,
        )
    )
    await session.execute(
        delete(CopilotRun).where(
            CopilotRun.encounter_id == encounter_id,
            CopilotRun.doctor_id == doctor_id,
        )
    )
    await session.execute(
        delete(Document).where(
            Document.encounter_id == encounter_id,
            Document.doctor_id == doctor_id,
        )
    )


@router.get("/encounters", response_model=list[EncounterListItem])
async def list_encounters(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[EncounterListItem]:
    result = await session.execute(
        select(Encounter)
        .where(Encounter.doctor_id == user.id)
        .order_by(Encounter.created_at.desc())
    )
    return [
        EncounterListItem(
            id=encounter.id,
            doctor_id=encounter.doctor_id,
            patient_id=encounter.patient_id,
            patient_connected=encounter.patient_connected,
            encounter_name=encounter.encounter_name,
            occurred_at=encounter.occurred_at,
        )
        for encounter in result.scalars().all()
    ]


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
async def get_encounter(
    encounter_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EncounterDetail:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    await record_audit_event(
        session,
        action="clinical.encounter_opened",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        patient_id=encounter.patient_id,
        encounter_id=encounter.id,
        resource_type="encounter",
        resource_id=encounter.id,
    )
    await session.commit()
    return _serialize_encounter(encounter)


@router.post("/encounters", response_model=EmptyEncounterResponse)
async def create_empty_encounter(
    _payload: EmptyPayload | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmptyEncounterResponse:
    now = datetime.now(timezone.utc)
    encounter = Encounter(
        doctor_id=user.id,
        patient_id=None,
        patient_connected=False,
        encounter_name="Encuentro Nuevo",
        occurred_at=now,
        created_at=now,
        audio_file_name=None,
        audio_uploaded_at=None,
        audio_expires_at=None,
        audio_duration_seconds=None,
        has_been_transcribed=False,
    )
    session.add(encounter)
    await session.flush()
    session.add_all(
        [
            new_empty_document(encounter_id=encounter.id, doctor_id=user.id, kind="context"),
            new_empty_document(
                encounter_id=encounter.id,
                doctor_id=user.id,
                kind="transcription",
            ),
        ]
    )
    await session.commit()
    return EmptyEncounterResponse(id=encounter.id)


@router.patch("/encounters/{encounter_id}", response_model=EncounterDetail)
async def update_encounter(
    encounter_id: int,
    payload: EncounterUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EncounterDetail:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    payload_dict = payload.model_dump(exclude_unset=True)

    if "patient_id" in payload_dict and payload_dict["patient_id"] is not None:
        patient_result = await session.execute(
            select(Patient)
            .join(PatientDoctor, PatientDoctor.patient_id == Patient.id)
            .where(
                Patient.id == payload_dict["patient_id"],
                PatientDoctor.doctor_id == user.id,
            )
        )
        if not patient_result.scalar_one_or_none():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    for field, value in payload_dict.items():
        setattr(encounter, field, value)

    await session.commit()
    await session.refresh(encounter)
    return _serialize_encounter(encounter)


@router.delete("/encounters/{encounter_id}", response_model=SuccessResponse)
async def delete_encounter(
    encounter_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessResponse:
    # Deuda: no emite audit events por documentos/encuentro borrados en cascada.
    # Ver docs/debt/encounter-delete-audit-trail.md
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    await _delete_encounter_dependents(
        session,
        encounter_id=encounter.id,
        doctor_id=user.id,
    )
    await session.delete(encounter)
    await session.commit()
    return SuccessResponse(success=True)


@router.post(
    "/encounters/{encounter_id}/audio/upload-url",
    response_model=AudioUploadResponse,
)
async def generate_upload_url(
    encounter_id: int,
    payload: AudioUploadRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AudioUploadResponse:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    if not settings.gcs_bucket_name:
        return AudioUploadResponse(success=False, error="GCS_BUCKET_NAME no configurado")

    filename = f"encounter_audio/{encounter_id}/{uuid.uuid4()}.webm"
    try:
        upload_url = generate_v4_upload_signed_url(
            settings=settings,
            gcs_object_name=filename,
            content_type="audio/webm;codecs=opus",
        )
    except Exception as exc:
        logger.exception(
            "Failed to generate encounter upload URL for encounter_id=%s",
            encounter_id,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=AudioUploadResponse(
                success=False,
                error=upload_url_user_error_message(exc),
            ).model_dump(),
        )

    now = datetime.now(timezone.utc)
    encounter.audio_file_name = filename
    encounter.audio_duration_seconds = payload.audio_duration_seconds
    encounter.audio_uploaded_at = now
    encounter.audio_expires_at = now + timedelta(hours=24)
    await record_audit_event(
        session,
        action="audio.upload_url_created",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        patient_id=encounter.patient_id,
        encounter_id=encounter.id,
        resource_type="audio_upload",
        resource_id=encounter.id,
    )
    await session.commit()
    return AudioUploadResponse(success=True, upload_url=upload_url, filename=filename)


@router.get(
    "/encounters/{encounter_id}/audio/exists",
    response_model=AudioExistsResponse,
)
async def check_audio_exists(
    encounter_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AudioExistsResponse:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    has_uploaded_audio_file = bool(
        encounter.audio_file_name and encounter.audio_file_name.strip()
    )
    has_sectioned_audio, sectioned_duration = await _get_sectioned_audio_summary(
        session,
        encounter_id=encounter.id,
        doctor_id=user.id,
    )
    has_audio = has_uploaded_audio_file or has_sectioned_audio
    is_expired = False
    if has_uploaded_audio_file and encounter.audio_expires_at:
        now = datetime.now(encounter.audio_expires_at.tzinfo)
        is_expired = encounter.audio_expires_at <= now

    return AudioExistsResponse(
        exists=has_audio,
        duration=encounter.audio_duration_seconds or sectioned_duration,
        has_been_transcribed=encounter.has_been_transcribed,
        expires_at=encounter.audio_expires_at if has_uploaded_audio_file else None,
        is_expired=is_expired,
    )


@router.delete("/encounters/{encounter_id}/audio", response_model=SuccessResponse)
async def delete_audio(
    encounter_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    if encounter.audio_file_name and settings.gcs_bucket_name:
        storage_client = get_storage_client(settings)
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        blob = bucket.blob(encounter.audio_file_name)
        if blob.exists():
            blob.delete()

    section_result = await session.execute(
        select(TranscriptionAudioSection.gcs_object_name)
        .select_from(TranscriptionRecordingSession)
        .join(
            TranscriptionAudioSection,
            TranscriptionAudioSection.recording_session_id
            == TranscriptionRecordingSession.id,
        )
        .where(
            TranscriptionRecordingSession.encounter_id == encounter.id,
            TranscriptionRecordingSession.doctor_id == user.id,
        )
    )
    section_object_names = list(section_result.scalars().all())
    if section_object_names and settings.gcs_bucket_name:
        storage_client = get_storage_client(settings)
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        for object_name in section_object_names:
            blob = bucket.blob(object_name)
            if blob.exists():
                blob.delete()

    transcription_document_result = await session.execute(
        select(Document)
        .where(
            Document.encounter_id == encounter.id,
            Document.doctor_id == user.id,
            Document.kind == "transcription",
        )
        .order_by(Document.id.asc())
    )
    transcription_document = transcription_document_result.scalars().first()

    encounter.audio_file_name = None
    encounter.audio_uploaded_at = None
    encounter.audio_expires_at = None
    encounter.audio_duration_seconds = None
    encounter.has_been_transcribed = False

    canonical_session = None
    if transcription_document:
        canonical_session = await get_canonical_recording_session_for_document(
            session,
            document_id=transcription_document.id,
            doctor_id=user.id,
        )

    if canonical_session:
        await reset_recording_session(
            session,
            recording_session=canonical_session,
            clear_document_content=True,
        )

    await session.execute(
        delete(TranscriptionAudioSection).where(
            TranscriptionAudioSection.recording_session_id.in_(
                select(TranscriptionRecordingSession.id).where(
                    TranscriptionRecordingSession.encounter_id == encounter.id,
                    TranscriptionRecordingSession.doctor_id == user.id,
                    TranscriptionRecordingSession.id
                    != (canonical_session.id if canonical_session else -1),
                )
            )
        )
    )
    await session.execute(
        delete(TranscriptionRecordingSession).where(
            TranscriptionRecordingSession.encounter_id == encounter.id,
            TranscriptionRecordingSession.doctor_id == user.id,
            TranscriptionRecordingSession.id != (canonical_session.id if canonical_session else -1),
        )
    )

    if transcription_document and not canonical_session:
        set_document_content_fields(
            transcription_document,
            content_markdown="",
            preferred_source="markdown",
        )
    await record_audit_event(
        session,
        action="audio.deleted",
        result="success",
        request=request,
        actor=actor_from_user(user),
        session_id=getattr(request.state, "auth_session_id", None),
        patient_id=encounter.patient_id,
        encounter_id=encounter.id,
        document_id=transcription_document.id if transcription_document else None,
        resource_type="audio",
        resource_id=encounter.id,
    )
    await session.commit()
    return SuccessResponse(success=True)
