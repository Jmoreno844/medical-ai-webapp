from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from .models import Encounter
from .schemas import (
    EncounterUpdate,
    EncountersListOut,
    EncounterDetailOut,
    EmptyEncounterResponse,
    AudioUploadRequest,
    AudioUploadResponse,
    AudioExistsResponse,
    EmptyPayload,
)
from datetime import date, datetime, timedelta
from apps.documents.models import Document
from django.conf import settings
import uuid

from apps.encounters.services.storage import get_storage_client


router = Router(tags=["encounters"])


@router.get("/encounters", response=List[EncountersListOut], auth=django_auth)
def list_encounters(request):
    encounters = Encounter.objects.filter(doctor=request.user)

    result = []
    for enc in encounters:
        result.append(
            {
                "id": enc.id,
                "doctor_id": enc.doctor.id if enc.doctor else None,
                "patient_id": enc.patient.id if enc.patient else None,
                "patient_connected": enc.patient_connected,
                "encounter_name": enc.encounter_name,
                "occurred_at": enc.occurred_at,
            }
        )
    return result


@router.get("/encounters/{encounter_id}", response=EncounterDetailOut, auth=django_auth)
def get_encounter(request, encounter_id: int):
    enc = get_object_or_404(Encounter, id=encounter_id)

    if enc.doctor_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    return {
        "id": enc.id,
        "doctor_id": enc.doctor.id if enc.doctor else None,
        "patient_id": enc.patient.id if enc.patient else None,
        "patient_connected": enc.patient_connected,
        "encounter_name": enc.encounter_name,
        "occurred_at": enc.occurred_at,
        "has_been_transcribed": enc.has_been_transcribed,
    }


@router.post("/encounters", response=EmptyEncounterResponse, auth=django_auth)
def create_empty_encounter(request, payload: EmptyPayload = None):
    enc = Encounter.objects.create(
        doctor_id=request.user.id,
        patient_id=None,
        encounter_name="Encuentro Nuevo",
        occurred_at=datetime.now(),
    )

    Document.objects.create(
        encounter=enc,
        kind="context",
        content="",
        doctor=request.user,
    )

    Document.objects.create(
        encounter=enc,
        kind="transcription",
        content="",
        doctor=request.user,
    )

    return {"id": enc.id}


@router.patch("/encounters/{encounter_id}", response=EncounterDetailOut, auth=django_auth)
def update_encounter(request, encounter_id: int, payload: EncounterUpdate):
    enc = get_object_or_404(Encounter, id=encounter_id)

    if enc.doctor_id != request.user.id:
        raise PermissionError("No puede modificar encuentros de otro médico")

    payload_dict = payload.dict(exclude_unset=True)

    if "patient_id" in payload_dict:
        if payload_dict["patient_id"] is not None:
            from apps.patients.models import Patient

            try:
                patient = Patient.objects.get(id=payload_dict["patient_id"])
                enc.patient = patient
            except Patient.DoesNotExist:
                raise ValueError(
                    f"Patient with ID {payload_dict['patient_id']} not found"
                )
        else:
            enc.patient = None

        del payload_dict["patient_id"]

    for field, value in payload_dict.items():
        setattr(enc, field, value)

    enc.save()

    return {
        "id": enc.id,
        "doctor_id": enc.doctor.id if enc.doctor else None,
        "patient_id": enc.patient.id if enc.patient else None,
        "patient_connected": enc.patient_connected,
        "encounter_name": enc.encounter_name,
        "occurred_at": enc.occurred_at,
        "has_been_transcribed": enc.has_been_transcribed,
    }


@router.delete("/encounters/{encounter_id}", response=dict, auth=django_auth)
def delete_encounter(request, encounter_id: int):
    enc = get_object_or_404(Encounter, id=encounter_id)

    if enc.doctor_id != request.user.id:
        raise PermissionError("No puede eliminar encuentros de otro médico")

    enc.delete()
    return {"success": True}


@router.post(
    "/encounters/{encounter_id}/audio/upload-url",
    response=AudioUploadResponse,
    auth=django_auth,
)
def generate_upload_url(request, encounter_id: int, payload: AudioUploadRequest):
    """Generate a signed URL for direct upload to Google Cloud Storage"""
    try:
        enc = get_object_or_404(Encounter, id=encounter_id)
        if request.user.id != enc.doctor.id:
            return {"success": False, "error": "Not authorized"}

        storage_client = get_storage_client()
        bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)

        filename = f"encounter_audio/{encounter_id}/{uuid.uuid4()}.mp3"
        blob = bucket.blob(filename)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=10),
            method="PUT",
            content_type="audio/webm;codecs=opus",
        )

        enc.audio_file_name = filename
        enc.audio_duration_seconds = payload.audio_duration_seconds
        enc.save()

        return {"success": True, "upload_url": url, "filename": filename}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get(
    "/encounters/{encounter_id}/audio/exists",
    response=AudioExistsResponse,
    auth=django_auth,
)
def check_audio_exists(request, encounter_id: int):
    enc = get_object_or_404(Encounter, id=encounter_id)

    if enc.doctor_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    has_audio = bool(enc.audio_file_name and enc.audio_file_name.strip())

    return {
        "exists": has_audio,
        "duration": enc.audio_duration_seconds or 0,
        "has_been_transcribed": enc.has_been_transcribed,
    }


@router.delete("/encounters/{encounter_id}/audio", response=dict, auth=django_auth)
def delete_audio(request, encounter_id: int):
    try:
        enc = get_object_or_404(Encounter, id=encounter_id)

        if enc.doctor_id != request.user.id:
            raise PermissionError("No puede modificar encuentros de otro médico")

        if enc.audio_file_name:
            storage_client = get_storage_client()
            bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
            blob = bucket.blob(enc.audio_file_name)
            if blob.exists():
                blob.delete()

        enc.audio_file_name = None
        enc.audio_uploaded_at = None
        enc.audio_expires_at = None
        enc.audio_duration_seconds = None
        enc.save()

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
