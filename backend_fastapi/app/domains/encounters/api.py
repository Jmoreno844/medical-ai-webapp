from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import Document, Encounter, Patient, User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.documents.service import new_empty_document
from app.integrations.storage import get_storage_client
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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EncounterDetail:
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
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
            select(Patient).where(Patient.id == payload_dict["patient_id"])
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
    encounter = await _get_encounter_or_404(
        session,
        encounter_id=encounter_id,
        doctor_id=user.id,
    )
    await session.execute(delete(Document).where(Document.encounter_id == encounter.id))
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

    storage_client = get_storage_client(settings)
    bucket = storage_client.bucket(settings.gcs_bucket_name)
    filename = f"encounter_audio/{encounter_id}/{uuid.uuid4()}.webm"
    blob = bucket.blob(filename)
    upload_url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=10),
        method="PUT",
        content_type="audio/webm;codecs=opus",
    )

    now = datetime.now(timezone.utc)
    encounter.audio_file_name = filename
    encounter.audio_duration_seconds = payload.audio_duration_seconds
    encounter.audio_uploaded_at = now
    encounter.audio_expires_at = now + timedelta(hours=24)
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
    has_audio = bool(encounter.audio_file_name and encounter.audio_file_name.strip())
    is_expired = False
    if has_audio and encounter.audio_expires_at:
        now = datetime.now(encounter.audio_expires_at.tzinfo)
        is_expired = encounter.audio_expires_at <= now

    return AudioExistsResponse(
        exists=has_audio,
        duration=encounter.audio_duration_seconds or 0,
        has_been_transcribed=encounter.has_been_transcribed,
        expires_at=encounter.audio_expires_at if has_audio else None,
        is_expired=is_expired,
    )


@router.delete("/encounters/{encounter_id}/audio", response_model=SuccessResponse)
async def delete_audio(
    encounter_id: int,
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

    encounter.audio_file_name = None
    encounter.audio_uploaded_at = None
    encounter.audio_expires_at = None
    encounter.audio_duration_seconds = None
    await session.commit()
    return SuccessResponse(success=True)

