from ninja import Router
from ninja.security import django_auth
from ninja.errors import HttpError
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import Http404
from apps.encounters.models import Encounter
from apps.documents.models import Document
import logging
import requests
from typing import Dict, Any

from apps.generative_ai.services.transcription_tasks import (
    TranscriptionTaskConfigurationError,
    enqueue_transcription_task,
    should_use_cloud_tasks,
)
from utils.service_jwt import (
    build_transcription_callback_payload,
    encode_service_jwt,
)
from .schemas import AudioDownloadResponse, TranscriptionRequest, TranscriptionResponse

logger = logging.getLogger(__name__)

router = Router()


@router.get(
    "/encounters/{encounter_id}/audio/gcs-uri",
    response=AudioDownloadResponse,
    auth=django_auth,
)
def get_audio_gcs_uri(request, encounter_id: int):
    """Get GCS URI for audio file to be used with Gemini API"""
    try:
        enc = get_object_or_404(Encounter, id=encounter_id)
        if request.user.id != enc.doctor.id:
            return {"success": False, "error": "Not authorized"}

        if not enc.audio_file_name:
            return {
                "success": False,
                "error": "No audio file associated with this encounter",
            }

        if enc.is_audio_expired():
            return {"success": False, "error": "Audio file has expired"}

        bucket_name = settings.GCS_BUCKET_NAME
        gcs_uri = f"gs://{bucket_name}/{enc.audio_file_name}"

        return {
            "success": True,
            "audio_uri": gcs_uri,
            "filename": enc.audio_file_name,
            "mime_type": "audio/mpeg",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/documents/{document_id}/transcription-token", auth=django_auth)
def authorize_transcription(request, document_id: int):
    if not request.user.is_authenticated:
        return {"success": False, "error": "Authentication required"}

    try:
        doc = get_object_or_404(Document, id=document_id)
        logger.info(f"Document verification for document_id={document_id}")

        if doc.doctor.id != request.user.id:
            logger.warning(
                f"Permission denied: document doctor {doc.doctor.id} != requesting doctor {request.user.id}"
            )
            return {
                "success": False,
                "error": "No tienes permiso para acceder a este documento",
            }

        token = encode_service_jwt(
            build_transcription_callback_payload(request.user.id, document_id)
        )
        logger.info(
            f"Token generated for user {request.user.id}, document {document_id}"
        )

        return {"success": True, "token": token}
    except Http404:
        logger.error(f"Document {document_id} not found")
        return {"success": False, "error": "Documento no encontrado"}


@router.post("/transcription/start", response=TranscriptionResponse, auth=django_auth)
def start_transcription(request, payload: TranscriptionRequest):
    encounter_id = payload.encounter_id
    document_id = payload.document_id

    try:
        enc = get_object_or_404(Encounter, id=encounter_id)
        if request.user.id != enc.doctor.id:
            logger.warning(f"Not authorized for encounter {encounter_id}")
            return TranscriptionResponse(
                success=False, error="Not authorized for this encounter"
            )

        if not enc.audio_file_name:
            logger.warning(f"No audio file for encounter {encounter_id}")
            return TranscriptionResponse(
                success=False, error="No audio file associated with this encounter"
            )

        if enc.is_audio_expired():
            logger.warning(f"Audio file expired for encounter {encounter_id}")
            return TranscriptionResponse(success=False, error="Audio file has expired")

        bucket_name = settings.GCS_BUCKET_NAME
        audio_uri = f"gs://{bucket_name}/{enc.audio_file_name}"

        doc = get_object_or_404(Document, id=document_id)
        logger.info(f"Document verification for document_id={document_id}")

        if doc.doctor.id != request.user.id:
            logger.warning(
                f"Permission denied: document doctor {doc.doctor.id} != requesting doctor {request.user.id}"
            )
            return TranscriptionResponse(
                success=False, error="No tienes permiso para acceder a este documento"
            )

        auth_token = encode_service_jwt(
            build_transcription_callback_payload(request.user.id, document_id)
        )

        cloud_function_payload = {
            "document_id": document_id,
            "audio_uri": audio_uri,
            "auth_token": auth_token,
        }

        try:
            if should_use_cloud_tasks():
                task_name = enqueue_transcription_task(cloud_function_payload)
                logger.info(
                    "Transcription task queued for document %s with task %s",
                    document_id,
                    task_name,
                )
                return TranscriptionResponse(
                    success=True,
                    message="Transcription queued successfully",
                )

            cloud_function_url = settings.TRANSCRIPTION_CLOUD_FUNCTION_URL
            response = requests.post(
                cloud_function_url,
                json=cloud_function_payload,
                timeout=30,
            )
            response.raise_for_status()
            logger.info(
                f"Transcription initiated for document {document_id} with encounter {encounter_id}"
            )

            return TranscriptionResponse(
                success=True, message="Transcription initiated successfully"
            )
        except TranscriptionTaskConfigurationError as e:
            logger.error("Cloud Tasks transcription misconfigured: %s", e)
            return TranscriptionResponse(success=False, error=str(e))
        except requests.RequestException as e:
            logger.error(f"Error calling transcription cloud function: {str(e)}")
            return TranscriptionResponse(
                success=False, error=f"Failed to initiate transcription: {str(e)}"
            )

    except Http404 as e:
        logger.error(f"Resource not found: {str(e)}")
        return TranscriptionResponse(success=False, error="Resource not found")
    except Exception as e:
        logger.error(f"Error in start_transcription: {str(e)}")
        return TranscriptionResponse(success=False, error=str(e))
