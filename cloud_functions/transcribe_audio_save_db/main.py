"""
Cloud Functions for transcription and document generation.
"""

import logging
import json
import functions_framework
from typing import Dict, Any

from services.transcription import transcribe_audio
from services.summarization import summarize_text
from services.django_api import update_document_content

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_document_id(document_id) -> tuple:
    """Validate document ID and return (is_valid, error_message)"""
    if not document_id:
        return False, "Missing document_id parameter"

    try:
        document_id = int(document_id)
        if document_id <= 0:
            return False, "document_id must be a positive integer"
        return True, None
    except ValueError:
        return False, "document_id must be an integer"


@functions_framework.http
def transcription_endpoint(request) -> tuple:
    """
    Cloud Function to transcribe audio from a signed URL and update a document.

    Expects:
        - document_id: ID of the document to update
        - audio_uri: A signed URL to the audio file in Google Cloud Storage
        - auth_token (optional): Auth token for Django API
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
        document_id = request_json.get("document_id")
        audio_uri = request_json.get("audio_uri")
        auth_token = request_json.get("auth_token")

        # Validate required parameters
        is_valid, error = validate_document_id(document_id)
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

        # Step 1: Transcribe the audio
        logger.info(f"Starting transcription for document {document_id}")
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
        logger.info(f"Updating document {document_id} with transcription")
        update_result = update_document_content(document_id, transcript, auth_token)

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
                    "document_id": document_id,
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


@functions_framework.http
def document_generation_endpoint(request) -> tuple:
    """
    Cloud Function to generate a document summary and update it.

    Expects:
        - document_id: ID of the document to update
        - text (optional): Text to summarize. If not provided, retrieves from document.
        - auth_token (optional): Auth token for Django API
    """
    # Log request details
    logger.info(f"Received document generation request: {request.method}")

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
        document_id = request_json.get("document_id")
        text = request_json.get("text")
        auth_token = request_json.get("auth_token")

        # Validate document ID
        is_valid, error = validate_document_id(document_id)
        if not is_valid:
            return (
                json.dumps({"success": False, "error": error}),
                400,
                {"Content-Type": "application/json"},
            )

        if not text:
            return (
                json.dumps({"success": False, "error": "Missing text parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        # Step 1: Generate summary
        logger.info(f"Generating summary for document {document_id}")
        summary_result = summarize_text(text)

        if not summary_result.get("success", False):
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": f"Summary generation failed: {summary_result.get('error', 'Unknown error')}",
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

        summary = summary_result.get("summary")

        # Step 2: Update the document with the summary
        logger.info(f"Updating document {document_id} with generated content")
        update_result = update_document_content(document_id, summary, auth_token)

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
                    "document_id": document_id,
                    "message": "Document generated and updated successfully",
                    "summary_preview": summary[:100] + "..."
                    if len(summary) > 100
                    else summary,
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        logger.error(
            f"Error processing document generation request: {str(e)}", exc_info=True
        )
        return (
            json.dumps({"success": False, "error": f"Internal server error: {str(e)}"}),
            500,
            {"Content-Type": "application/json"},
        )
