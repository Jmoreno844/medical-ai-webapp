import base64
import os
import tempfile
from ninja import Router, File, UploadedFile
from ninja.security import django_auth
from ninja.errors import HttpError
from ninja.responses import Response
from typing import Dict

from apps.generative_ai.services.transcription_service import process_uploaded_audio

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
    request, file: UploadedFile = File(...), format: str = "timecode"
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
