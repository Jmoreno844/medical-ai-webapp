from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.schemas import SuccessResponse
from app.db.models import (
    Encounter,
    Patient,
    PatientDoctor,
    TranscriptionAudioSection,
    TranscriptionRecordingSession,
    User,
)
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.encounters.api import _delete_encounter_dependents
from app.domains.patients.schemas import PatientCreate, PatientResponse, PatientUpdate
from app.integrations.storage import get_storage_client

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialize_patient(patient: Patient) -> PatientResponse:
    return PatientResponse(id=patient.id, name=patient.name, summary=patient.summary)


def _require_doctor(user: User) -> None:
    if user.role != "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only doctors can manage patients")


async def _get_patient_for_doctor(
    session: AsyncSession,
    *,
    patient_id: int,
    doctor_id: int,
) -> Patient:
    result = await session.execute(
        select(Patient)
        .join(PatientDoctor, PatientDoctor.patient_id == Patient.id)
        .where(Patient.id == patient_id, PatientDoctor.doctor_id == doctor_id)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


async def _delete_patient_audio_blobs_best_effort(
    *,
    object_names: list[str],
    settings: Settings,
) -> None:
    if not object_names or not settings.gcs_bucket_name:
        return

    try:
        storage_client = get_storage_client(settings)
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        for object_name in object_names:
            blob = bucket.blob(object_name)
            if blob.exists():
                blob.delete()
    except Exception:
        logger.warning(
            "Failed to delete one or more patient audio blobs from GCS",
            exc_info=True,
        )


async def delete_patient_for_doctor(
    session: AsyncSession,
    *,
    patient_id: int,
    doctor_id: int,
) -> None:
    await _get_patient_for_doctor(
        session,
        patient_id=patient_id,
        doctor_id=doctor_id,
    )

    encounter_result = await session.execute(
        select(Encounter.id).where(
            Encounter.patient_id == patient_id,
            Encounter.doctor_id == doctor_id,
        )
    )
    encounter_ids = list(encounter_result.scalars().all())

    for encounter_id in encounter_ids:
        await _delete_encounter_dependents(
            session,
            encounter_id=encounter_id,
            doctor_id=doctor_id,
        )

    if encounter_ids:
        await session.execute(
            delete(Encounter).where(
                Encounter.id.in_(encounter_ids),
                Encounter.doctor_id == doctor_id,
            )
        )

    await session.execute(
        delete(PatientDoctor).where(
            PatientDoctor.patient_id == patient_id,
            PatientDoctor.doctor_id == doctor_id,
        )
    )

    remaining_links_result = await session.execute(
        select(func.count(PatientDoctor.id)).where(PatientDoctor.patient_id == patient_id)
    )
    if (remaining_links_result.scalar_one() or 0) == 0:
        await session.execute(delete(Patient).where(Patient.id == patient_id))


async def _collect_patient_audio_object_names(
    session: AsyncSession,
    *,
    patient_id: int,
    doctor_id: int,
) -> list[str]:
    uploaded_audio_result = await session.execute(
        select(Encounter.audio_file_name).where(
            Encounter.patient_id == patient_id,
            Encounter.doctor_id == doctor_id,
            Encounter.audio_file_name.is_not(None),
        )
    )
    section_audio_result = await session.execute(
        select(TranscriptionAudioSection.gcs_object_name)
        .select_from(TranscriptionRecordingSession)
        .join(
            TranscriptionAudioSection,
            TranscriptionAudioSection.recording_session_id
            == TranscriptionRecordingSession.id,
        )
        .join(Encounter, Encounter.id == TranscriptionRecordingSession.encounter_id)
        .where(
            Encounter.patient_id == patient_id,
            TranscriptionRecordingSession.doctor_id == doctor_id,
        )
    )
    return [
        object_name
        for object_name in [
            *uploaded_audio_result.scalars().all(),
            *section_audio_result.scalars().all(),
        ]
        if object_name
    ]


@router.post("/patients", response_model=PatientResponse)
async def create_patient(
    payload: PatientCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PatientResponse:
    _require_doctor(user)
    now = datetime.now(timezone.utc)
    patient = Patient(name=payload.name, summary=payload.summary, created_at=now)
    session.add(patient)
    await session.flush()
    session.add(PatientDoctor(doctor_id=user.id, patient_id=patient.id, created_at=now))
    await session.commit()
    await session.refresh(patient)
    return _serialize_patient(patient)


@router.put("/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PatientResponse:
    _require_doctor(user)
    patient = await _get_patient_for_doctor(
        session,
        patient_id=patient_id,
        doctor_id=user.id,
    )
    patient.name = payload.name
    if payload.summary is not None:
        patient.summary = payload.summary
    await session.commit()
    await session.refresh(patient)
    return _serialize_patient(patient)


@router.get("/patients/search", response_model=list[PatientResponse])
async def search_patients(
    name: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PatientResponse]:
    _require_doctor(user)
    result = await session.execute(
        select(Patient)
        .join(PatientDoctor, PatientDoctor.patient_id == Patient.id)
        .where(
            PatientDoctor.doctor_id == user.id,
            Patient.name.ilike(f"%{name}%"),
        )
        .order_by(Patient.name)
    )
    return [_serialize_patient(patient) for patient in result.scalars().unique().all()]


@router.delete("/patients/{patient_id}", response_model=SuccessResponse)
async def delete_patient(
    patient_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse:
    _require_doctor(user)
    object_names = await _collect_patient_audio_object_names(
        session,
        patient_id=patient_id,
        doctor_id=user.id,
    )
    await delete_patient_for_doctor(
        session,
        patient_id=patient_id,
        doctor_id=user.id,
    )
    await session.commit()
    await _delete_patient_audio_blobs_best_effort(
        object_names=object_names,
        settings=settings,
    )
    return SuccessResponse(success=True)
