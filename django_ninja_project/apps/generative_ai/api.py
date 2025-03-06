import base64
import os
import tempfile
from ninja import Router, File, UploadedFile
from ninja.security import django_auth
from ninja.errors import HttpError
from ninja.responses import Response
from typing import Dict
from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.generative_ai.services.transcription_service import process_uploaded_audio
from apps.generative_ai.schemas import TranscriptionResponse, GeminiResponse

# Define allowed file types for security
ALLOWED_AUDIO_MIME_TYPES = [
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
]
# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

router = Router()


@router.post(
    "/transcribe", auth=django_auth, response={200: Dict, 400: Dict, 500: Dict}
)
def transcribe_audio_endpoint(
    request, file: UploadedFile = File(...), format: str = "speakers"
):
    """
    Transcribe an uploaded audio file into text.

    Args:
        request: The HTTP request
        file: The uploaded audio file
        format: The format for transcript output (default: "timecode")

    Returns:
        Dict containing the transcription and metadata

    Raises:
        HttpError: If file type not allowed, exceeds size limit, or processing fails
    """
    # Validate user is authenticated (belt and suspenders - auth decorator should handle this)
    if not request.user.is_authenticated:
        return 401, {"detail": "Authentication required"}

    # Security checks
    if file.content_type not in ALLOWED_AUDIO_MIME_TYPES:
        return 400, {
            "detail": f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_AUDIO_MIME_TYPES)}"
        }

    if file.size > MAX_FILE_SIZE:
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        return 400, {"detail": f"File too large. Maximum size is {max_size_mb} MB"}

    try:
        # Process the uploaded audio file
        result = process_uploaded_audio(file, format)
        return 200, result
    except ValueError as e:
        return 400, {"detail": str(e)}
    except Exception as e:
        # Log the error but don't expose internal details
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error processing audio: {str(e)}")
        return 500, {"detail": "Failed to process audio file"}


@router.post(
    "/transcribir/{documento_id}",
    auth=django_auth,
    response={200: Dict, 400: Dict, 401: Dict, 403: Dict, 404: Dict, 500: Dict},
)
def transcribir_documento(
    request, documento_id: int, file: UploadedFile = File(...), format: str = "speakers"
):
    """
    Transcribe an uploaded audio file and update the specified document's content.
    Uses Celery to process the transcription asynchronously.

    This endpoint:
    1. Verifies user authentication
    2. Checks document exists and is of type 'transcripcion'
    3. Verifies the user has permission (document's id_medico matches user ID)
    4. Processes the uploaded audio file using Gemini API
    5. Updates the document's contenido field with the transcription

    Args:
        request: The HTTP request
        documento_id: ID of the document to transcribe
        file: The uploaded audio file
        format: The format for transcript output (default: "speakers")

    Returns:
        Dict containing success status and message

    Security:
        - Requires authentication
        - Validates user owns the document
        - Validates document type
        - Validates file type and size
    """
    # Verify user is authenticated
    if not request.user.is_authenticated:
        return 401, {"detail": "Authentication required"}

    # Security checks for the uploaded file
    if file.content_type not in ALLOWED_AUDIO_MIME_TYPES:
        return 400, {
            "detail": f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_AUDIO_MIME_TYPES)}"
        }

    if file.size > MAX_FILE_SIZE:
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        return 400, {"detail": f"File too large. Maximum size is {max_size_mb} MB"}

    try:
        import logging

        logger = logging.getLogger(__name__)

        # Get user ID - try both id and pk attributes
        user_id = getattr(request.user, "id", None)
        if user_id is None:
            user_id = getattr(request.user, "pk", None)

        if user_id is None:
            return 500, {"detail": "Could not determine user ID"}

        # First check if the document exists and the user has permission
        from apps.generative_ai.services.document_transcription_service import (
            get_document_for_transcription,
        )

        try:
            documento = get_document_for_transcription(documento_id, user_id)
        except Http404:
            return 404, {"detail": "Document not found"}
        except PermissionDenied:
            return 403, {
                "detail": "Access denied: you don't have permission to transcribe this document"
            }
        except ValueError as e:
            return 400, {"detail": str(e)}

        # Save the uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            for chunk in file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Import and queue the Celery task
        from apps.generative_ai.tasks import process_transcription_task

        task = process_transcription_task.delay(documento_id, temp_file_path, format)

        return 200, {
            "success": True,
            "message": "Document transcription started",
            "document_id": documento_id,
            "task_id": task.id,
        }

    except Exception as e:
        # Log the error but don't expose internal details
        logger.error(
            f"Error initiating transcription for document {documento_id}: {str(e)}"
        )
        return 500, {"detail": "Failed to start transcription process"}
