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
from apps.generative_ai.services.cloud_gemini_service import generate_content

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
    This endpoint processes the transcription synchronously in the request.

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
        Dict containing the transcription result and metadata

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
            transcribe_document_with_uploaded_file,
        )

        try:
            # Validate document and permissions
            documento = get_document_for_transcription(documento_id, user_id)

            # Process the transcription directly
            result = transcribe_document_with_uploaded_file(
                documento_id, user_id, file, format
            )

            return 200, {
                "success": True,
                "document_id": documento_id,
                "transcript": result.get("transcript", ""),
                "duration": result.get("duration", 0),
                "message": "Document transcription completed successfully",
            }

        except Http404:
            return 404, {"detail": "Document not found"}
        except PermissionDenied:
            return 403, {
                "detail": "Access denied: you don't have permission to transcribe this document"
            }
        except ValueError as e:
            return 400, {"detail": str(e)}

    except Exception as e:
        # Log the error but don't expose internal details
        logger = logging.getLogger(__name__)
        logger.error(
            f"Error processing transcription for document {documento_id}: {str(e)}"
        )
        return 500, {"detail": "Failed to process transcription"}


@router.post(
    "/generate-content", auth=django_auth, response={200: Dict, 400: Dict, 500: Dict}
)
def generate_content_endpoint(request, data: Dict):
    """
    Generate content using Gemini AI via the Cloud Function.

    Args:
        request: The HTTP request
        data: Dictionary containing prompt and optional parameters

    Returns:
        Dict containing the generated content

    Raises:
        HttpError: If the request is invalid or processing fails
    """
    # Verify user is authenticated
    if not request.user.is_authenticated:
        return 401, {"detail": "Authentication required"}

    # Extract parameters
    prompt = data.get("prompt")
    if not prompt:
        return 400, {"detail": "Prompt is required"}

    model_name = data.get("model")
    generation_config = data.get("generation_config")

    try:
        # Call the Cloud Function via our service
        result = generate_content(prompt, model_name, generation_config)
        return 200, result
    except ConnectionError as e:
        return 503, {"detail": str(e)}
    except ValueError as e:
        return 400, {"detail": str(e)}
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error generating content: {str(e)}")
        return 500, {"detail": "Failed to generate content"}
