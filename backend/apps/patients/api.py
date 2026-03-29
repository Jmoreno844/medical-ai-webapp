from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from django.http import HttpRequest
from django.db.models import Q
from .schemas import PatientCreate, PatientResponse, PatientUpdate
from .models import Patient, PatientDoctor
from apps.users.models import User, UserRole
from ninja.security import django_auth

router = Router(tags=["patients"])


@router.post("/patients", response=PatientResponse, auth=django_auth)
def create_patient(request: HttpRequest, data: PatientCreate):
    user = request.auth

    if user.role != UserRole.DOCTOR:
        return {"detail": "Only doctors can create patients"}, 403

    patient = Patient.objects.create(name=data.name, summary=data.summary)

    PatientDoctor.objects.create(doctor=user, patient=patient)

    return patient


@router.put("/patients/{patient_id}", response=PatientResponse, auth=django_auth)
def update_patient(request: HttpRequest, patient_id: int, data: PatientUpdate):
    user = request.auth

    if user.role != UserRole.DOCTOR:
        return {"detail": "Only doctors can edit patients"}, 403

    patient = get_object_or_404(Patient, id=patient_id)

    relationship_exists = PatientDoctor.objects.filter(
        doctor=user, patient=patient
    ).exists()

    if not relationship_exists:
        return {"detail": "You are not authorized to edit this patient"}, 403

    patient.name = data.name
    if data.summary is not None:
        patient.summary = data.summary
    patient.save()

    return patient


@router.get("/patients/search", response=List[PatientResponse], auth=django_auth)
def search_patients(request: HttpRequest, name: str = ""):
    user = request.auth

    if user.role != UserRole.DOCTOR:
        return {"detail": "Only doctors can search patients"}, 403

    patients = Patient.objects.filter(
        patientdoctor_set__doctor=user,
        name__icontains=name,
    ).distinct()

    return list(patients)
