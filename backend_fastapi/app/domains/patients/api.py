from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Patient, PatientDoctor, User
from app.db.session import get_db_session
from app.domains.auth.service import get_current_user
from app.domains.patients.schemas import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter()


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

