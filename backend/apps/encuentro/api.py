from ninja import Router
from typing import List
from django.shortcuts import get_object_or_404
from ninja.security import django_auth
from .models import Encuentro
from .schemas import (
    EncuentroCreate,
    EncuentroUpdate,
    EncuentrosOut,
    SingleEncuentroOut,
    EmptyEncuentroResponse,
    AudioUploadRequest,
    AudioUploadResponse,
    AudioExistsResponse,
    EmptyPayload,
)
from datetime import date, datetime, timedelta
from apps.documentos.models import Documento  # Import the Documento model
from django.conf import settings
import uuid

from apps.encuentro.services.storage import get_storage_client


router = Router(tags=["encuentros"])


@router.get("/encuentros", response=List[EncuentrosOut], auth=django_auth)
def list_encuentros(request):
    # Only return encounters for the authenticated doctor
    encounters = Encuentro.objects.filter(id_medico=request.user.id)

    # Convert each encounter to a dictionary with explicit ID values
    result = []
    for encuentro in encounters:
        result.append(
            {
                "id": encuentro.id,
                "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
                "id_paciente": encuentro.id_paciente.id
                if encuentro.id_paciente
                else None,
                "paciente_conectado": encuentro.paciente_conectado,
                "nombre_encuentro": encuentro.nombre_encuentro,
                "fecha": encuentro.fecha,
            }
        )
    return result


@router.get("/encuentros/{encuentro_id}", response=SingleEncuentroOut, auth=django_auth)
def get_encuentro(request, encuentro_id: int):
    # Get the encounter or return 404
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    # Return a dictionary with explicit ID values
    return {
        "id": encuentro.id,
        "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
        "id_paciente": encuentro.id_paciente.id if encuentro.id_paciente else None,
        "paciente_conectado": encuentro.paciente_conectado,
        "nombre_encuentro": encuentro.nombre_encuentro,
        "fecha": encuentro.fecha,
        "has_been_transcribed": encuentro.has_been_transcribed,
    }


@router.post("/encuentros", response=EmptyEncuentroResponse, auth=django_auth)
def create_empty_encuentro(request, payload: EmptyPayload = None):
    # Create the encounter
    encuentro = Encuentro.objects.create(
        id_medico_id=request.user.id,
        id_paciente_id=None,  # Will be set later
        nombre_encuentro="Encuentro Nuevo",
        fecha=datetime.now(),
    )

    # Create contexto document
    Documento.objects.create(
        id_encuentro=encuentro,
        tipo="contexto",
        contenido="",
        id_medico=request.user,
    )

    # Create transcripcion document
    Documento.objects.create(
        id_encuentro=encuentro,
        tipo="transcripcion",
        contenido="",
        id_medico=request.user,
    )

    return {"id": encuentro.id}


@router.patch(
    "/encuentros/{encuentro_id}", response=SingleEncuentroOut, auth=django_auth
)
def update_encuentro(request, encuentro_id: int, payload: EncuentroUpdate):
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede modificar encuentros de otro médico")

    # Get a copy of the payload as dict
    payload_dict = payload.dict(exclude_unset=True)

    # Handle the id_paciente field specially
    if "id_paciente" in payload_dict:
        if payload_dict["id_paciente"] is not None:
            # Get the actual Paciente instance
            from apps.pacientes.models import Paciente

            try:
                paciente = Paciente.objects.get(id=payload_dict["id_paciente"])
                encuentro.id_paciente = paciente
            except Paciente.DoesNotExist:
                raise ValueError(
                    f"Patient with ID {payload_dict['id_paciente']} not found"
                )
        else:
            # Handle setting to None (removing patient)
            encuentro.id_paciente = None

        # Remove from dict so we don't process it again
        del payload_dict["id_paciente"]

    # Update the remaining fields
    for field, value in payload_dict.items():
        setattr(encuentro, field, value)

    encuentro.save()

    # Return a dictionary with explicit ID values, not the model instance
    return {
        "id": encuentro.id,
        "id_medico": encuentro.id_medico.id if encuentro.id_medico else None,
        "id_paciente": encuentro.id_paciente.id if encuentro.id_paciente else None,
        "paciente_conectado": encuentro.paciente_conectado,
        "nombre_encuentro": encuentro.nombre_encuentro,
        "fecha": encuentro.fecha,
        "has_been_transcribed": encuentro.has_been_transcribed,
    }


@router.delete("/encuentros/{encuentro_id}", response=dict, auth=django_auth)
def delete_encuentro(request, encuentro_id: int):
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede eliminar encuentros de otro médico")

    encuentro.delete()
    return {"success": True}


## Audio and AI


@router.post(
    "/generar_url_audio/{encuentro_id}", response=AudioUploadResponse, auth=django_auth
)
def generate_upload_url(request, encuentro_id: int, payload: AudioUploadRequest):
    """Generate a signed URL for direct upload to Google Cloud Storage"""
    try:
        # Verify user has permission to this encounter
        encuentro = get_object_or_404(Encuentro, id=encuentro_id)
        if request.user.id != encuentro.id_medico.id:
            return {"success": False, "error": "Not authorized"}

        # Initialize GCS client based on environment
        storage_client = get_storage_client()
        bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)

        # Generate unique filename
        filename = f"encounter_audio/{encuentro_id}/{uuid.uuid4()}.mp3"
        blob = bucket.blob(filename)

        # Generate signed URL valid for 10 minutes (for upload)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=10),
            method="PUT",
            content_type="audio/webm;codecs=opus",
        )

        # Update the encuentro with the filename
        encuentro.audio_file_name = filename
        encuentro.audio_duration_seconds = payload.audio_duration_seconds
        encuentro.save()

        # Return the signed URL and filename to the frontend
        return {"success": True, "upload_url": url, "filename": filename}

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get(
    "encuentros/audio_exists/{encuentro_id}",
    response=AudioExistsResponse,
    auth=django_auth,
)
def check_audio_exists(request, encuentro_id: int):
    """Check if the encounter has an assigned audio file"""
    # Get the encounter or return 404
    encuentro = get_object_or_404(Encuentro, id=encuentro_id)

    # Verify the doctor owns this encounter
    if encuentro.id_medico_id != request.user.id:
        raise PermissionError("No puede acceder a encuentros de otro médico")

    # Check if audio file exists (not null or empty)
    has_audio = bool(encuentro.audio_file_name and encuentro.audio_file_name.strip())

    # Return response with exists flag and duration
    return {
        "exists": has_audio,
        "duration": encuentro.audio_duration_seconds or 0,
        "has_been_transcribed": encuentro.has_been_transcribed,
    }


@router.delete(
    "/encuentros/delete_audio/{encuentro_id}", response=dict, auth=django_auth
)
def delete_audio(request, encuentro_id: int):
    """Delete audio data for an encounter from database and cloud storage"""
    try:
        # Get the encounter or return 404
        encuentro = get_object_or_404(Encuentro, id=encuentro_id)

        # Verify the doctor owns this encounter
        if encuentro.id_medico_id != request.user.id:
            raise PermissionError("No puede modificar encuentros de otro médico")

        # Check if there's an audio file to delete
        if encuentro.audio_file_name:
            # Initialize GCS client based on environment
            storage_client = get_storage_client()
            bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)

            # Delete the blob from cloud storage
            blob = bucket.blob(encuentro.audio_file_name)
            if blob.exists():
                blob.delete()

        # Clear audio fields in the database
        encuentro.audio_file_name = None
        encuentro.audio_uploaded_at = None
        encuentro.audio_expires_at = None
        encuentro.audio_duration_seconds = None
        encuentro.save()

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
