from ninja import Router, File, UploadedFile, Body
from ninja.security import django_auth
from ninja.errors import HttpError
from ninja.responses import Response
from .schemas import AudioDownloadResponse, TranscriptionRequest, TranscriptionResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import Http404
from apps.encuentro.models import Encuentro
from apps.documentos.models import Documento
import logging
import requests
from typing import Dict, Any

from utils.service_jwt import (
    build_transcription_callback_payload,
    encode_service_jwt,
)

logger = logging.getLogger(__name__)


router = Router()


@router.get(
    "/obtener_url_audio/{encuentro_id}",
    response=AudioDownloadResponse,
    auth=django_auth,
)
def get_audio_download_url(request, encuentro_id: int):
    """Get GCS URI for audio file to be used with Gemini API"""
    try:
        # Verify user has permission to this encounter
        encuentro = get_object_or_404(Encuentro, id=encuentro_id)
        if request.user.id != encuentro.id_medico.id:
            return {"success": False, "error": "Not authorized"}

        # Check if audio exists
        if not encuentro.audio_file_name:
            return {
                "success": False,
                "error": "No audio file associated with this encounter",
            }

        # Check if audio has expired
        if encuentro.is_audio_expired():
            return {"success": False, "error": "Audio file has expired"}

        # Generate GCS URI format - use the full audio_file_name which already contains the encounter path
        bucket_name = settings.GCS_BUCKET_NAME
        gcs_uri = f"gs://{bucket_name}/{encuentro.audio_file_name}"

        # Return GCS URI format instead of signed URL
        return {
            "success": True,
            "audio_uri": gcs_uri,  # Change field name from download_url to gcs_uri
            "filename": encuentro.audio_file_name,
            "mime_type": "audio/mpeg",  # Changed to audio/mpeg to match transcription service
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# This endpoint uses Django auth
@router.post("/autorizar-documento/{documento_id}", auth=django_auth)
def authorize_transcription(request, documento_id: int):
    """Endpoint that requires Django auth and generates a JWT token"""
    # Check if user is authenticated (Django auth)
    if not request.user.is_authenticated:
        return {"success": False, "error": "Authentication required"}

    try:
        # Verify the document exists
        documento = get_object_or_404(Documento, id=documento_id)
        logger.info(f"Document verification for documento_id={documento_id}")

        # Verify the document belongs to the authenticated doctor
        if documento.id_medico.id != request.user.id:
            logger.warning(
                f"Permission denied: documento doctor {documento.id_medico.id} != requesting doctor {request.user.id}"
            )
            return {
                "success": False,
                "error": "No tienes permiso para acceder a este documento",
            }

        # Same claims as iniciar_transcripcion / Cloud Function callbacks
        token = encode_service_jwt(
            build_transcription_callback_payload(request.user.id, documento_id)
        )
        logger.info(
            f"Token generated for user {request.user.id}, documento {documento_id}"
        )

        return {"success": True, "token": token}
    except Http404:
        logger.error(f"Documento {documento_id} not found")
        return {"success": False, "error": "Documento no encontrado"}


@router.post("/iniciar_transcripcion", response=TranscriptionResponse, auth=django_auth)
def iniciar_transcripcion(request, payload: TranscriptionRequest):
    """
    Initiate transcription of an audio file for a document

    1. Validates user permissions for both encounter and document
    2. Gets audio file URI from the encounter
    3. Generates authorization token
    4. Calls the cloud function for transcription
    """
    # Extract the IDs from the payload using proper schema
    encuentro_id = payload.id_encuentro
    documento_id = payload.id_documento

    try:
        # Verify encounter permissions and get audio URI
        encuentro = get_object_or_404(Encuentro, id=encuentro_id)
        if request.user.id != encuentro.id_medico.id:
            logger.warning(f"Not authorized for encounter {encuentro_id}")
            return TranscriptionResponse(
                success=False, error="Not authorized for this encounter"
            )

        # Check if audio exists
        if not encuentro.audio_file_name:
            logger.warning(f"No audio file for encounter {encuentro_id}")
            return TranscriptionResponse(
                success=False, error="No audio file associated with this encounter"
            )

        # Check if audio has expired
        if encuentro.is_audio_expired():
            logger.warning(f"Audio file expired for encounter {encuentro_id}")
            return TranscriptionResponse(success=False, error="Audio file has expired")

        # Generate GCS URI
        bucket_name = settings.GCS_BUCKET_NAME
        audio_uri = f"gs://{bucket_name}/{encuentro.audio_file_name}"

        # Verify document permissions
        documento = get_object_or_404(Documento, id=documento_id)
        logger.info(f"Document verification for documento_id={documento_id}")

        if documento.id_medico.id != request.user.id:
            logger.warning(
                f"Permission denied: documento doctor {documento.id_medico.id} != requesting doctor {request.user.id}"
            )
            return TranscriptionResponse(
                success=False, error="No tienes permiso para acceder a este documento"
            )

        auth_token = encode_service_jwt(
            build_transcription_callback_payload(request.user.id, documento_id)
        )

        # Prepare cloud function request payload
        cloud_function_payload = {
            "id_documento": documento_id,
            "audio_uri": audio_uri,
            "auth_token": auth_token,
        }

        # Call the cloud function
        cloud_function_url = settings.TRANSCRIPTION_CLOUD_FUNCTION_URL
        try:
            response = requests.post(cloud_function_url, json=cloud_function_payload)
            response.raise_for_status()
            logger.info(
                f"Transcription initiated for document {documento_id} with encounter {encuentro_id}"
            )

            # Update the encounter with transcription status
            encuentro.has_been_transcribed = True
            encuentro.save()
            return TranscriptionResponse(
                success=True, message="Transcription initiated successfully"
            )
        except requests.RequestException as e:
            logger.error(f"Error calling transcription cloud function: {str(e)}")
            return TranscriptionResponse(
                success=False, error=f"Failed to initiate transcription: {str(e)}"
            )

    except Http404 as e:
        logger.error(f"Resource not found: {str(e)}")
        return TranscriptionResponse(success=False, error="Resource not found")
    except Exception as e:
        logger.error(f"Error in iniciar_transcripcion: {str(e)}")
        return TranscriptionResponse(success=False, error=str(e))
