"""
Cloud Function endpoint for audio transcription.
"""

import logging
import json
from services.transcription.audio_processor import transcribe_audio
from services.django_api import update_document_content

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_id_documento(id_documento) -> tuple:
    """Validate document ID and return (is_valid, error_message)"""
    if not id_documento:
        return False, "Missing id_documento parameter"

    try:
        id_documento = int(id_documento)
        if id_documento <= 0:
            return False, "id_documento must be a positive integer"
        return True, None
    except ValueError:
        return False, "id_documento must be an integer"


def transcription_endpoint(request) -> tuple:
    """
    Cloud Function to transcribe audio from a signed URL and update a document.

    Expects:
        - id_documento: ID of the document to update
        - audio_uri: A signed URL to the audio file in Google Cloud Storage
        - token_auth: Auth token for Django API
    """
    # Log request details
    logger.info(f"Received transcription request: {request.method}")

    # Only allow POST requests
    if request.method != "POST":
        return (
            json.dumps({"success": False, "error": "Only POST method is allowed"}),
            405,
            {"Content-Type": "application/json"},
        )

    try:
        # Parse request data
        request_json = request.get_json(silent=True) or {}
        id_documento = request_json.get("id_documento")
        audio_uri = request_json.get("audio_uri")
        token_auth = request_json.get("auth_token")

        # Validate required parameters
        is_valid, error = validate_id_documento(id_documento)
        if not is_valid:
            return (
                json.dumps({"success": False, "error": error}),
                400,
                {"Content-Type": "application/json"},
            )

        if not audio_uri:
            return (
                json.dumps({"success": False, "error": "Missing audio_uri parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        if not token_auth or not str(token_auth).strip():
            return (
                json.dumps(
                    {"success": False, "error": "Missing auth_token parameter"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        # Step 1: Transcribe the audio
        logger.info(f"Starting transcription for document {id_documento}")
        transcription_result = transcribe_audio(audio_uri)

        if not transcription_result.get("success", False):
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": f"Transcription failed: {transcription_result.get('error', 'Unknown error')}",
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

        transcript = transcription_result.get("transcript")

        # Step 2: Update the document with the transcription
        logger.info(f"Updating document {id_documento} with transcription")
        update_result = update_document_content(id_documento, transcript, token_auth)

        if not update_result.get("success", False):
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": f"Failed to update document: {update_result.get('error', 'Unknown error')}",
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

        # Return success response
        return (
            json.dumps(
                {
                    "success": True,
                    "id_documento": id_documento,
                    "message": "Audio transcribed and document updated successfully",
                    "transcript_preview": transcript[:100] + "..."
                    if len(transcript) > 100
                    else transcript,
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        logger.error(f"Error processing transcription request: {str(e)}", exc_info=True)
        return (
            json.dumps({"success": False, "error": f"Internal server error: {str(e)}"}),
            500,
            {"Content-Type": "application/json"},
        )
