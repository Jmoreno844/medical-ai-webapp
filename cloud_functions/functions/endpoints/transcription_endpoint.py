"""
Cloud Function endpoint for audio transcription.
"""

import logging
import json

from langsmith_tracing import trace_operation
from services.transcription.audio_processor import transcribe_audio
from services.django_api import update_document_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _langsmith_request_inputs(request) -> dict:
    request_json = request.get_json(silent=True) or {}
    audio_uri = str(request_json.get("audio_uri") or "")
    audio_scheme = audio_uri.split(":", 1)[0] if audio_uri else None
    return {
        "method": request.method,
        "document_id": request_json.get("document_id"),
        "audio_scheme": audio_scheme,
        "has_auth_token": bool(request_json.get("auth_token")),
    }


def _langsmith_request_outputs(response: tuple) -> dict:
    body, status_code, _headers = response
    payload = json.loads(body)
    return {
        "status_code": status_code,
        "success": bool(payload.get("success")),
        "document_id": payload.get("document_id"),
        "error_code": payload.get("error_code"),
    }


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


def transcription_endpoint(request) -> tuple:
    """
    Cloud Function to transcribe audio from GCS URI and update a document.

    Expects:
        - document_id: ID of the document to update
        - audio_uri: gs:// URI to the audio file
        - auth_token: JWT for Django API
    """
    from tracing import configure_tracing, run_with_request_span

    configure_tracing()
    return run_with_request_span(
        request, "cloud_functions.transcription", _transcription_endpoint_impl
    )


@trace_operation(
    name="cloud_functions.transcription_request",
    run_type="chain",
    process_inputs=_langsmith_request_inputs,
    process_outputs=_langsmith_request_outputs,
    tags=["transcription", "http"],
)
def _transcription_endpoint_impl(request) -> tuple:
    logger.info(f"Received transcription request: {request.method}")

    if request.method != "POST":
        return (
            json.dumps({"success": False, "error": "Only POST method is allowed"}),
            405,
            {"Content-Type": "application/json"},
        )

    try:
        request_json = request.get_json(silent=True) or {}
        document_id = request_json.get("document_id")
        audio_uri = request_json.get("audio_uri")
        token_auth = request_json.get("auth_token")

        is_valid, error = validate_document_id(document_id)
        if not is_valid:
            return (
                json.dumps({"success": False, "error": error}),
                400,
                {"Content-Type": "application/json"},
            )

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("document_id", int(document_id))
        except Exception:
            pass

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

        logger.info(f"Starting transcription for document {document_id}")
        transcription_result = transcribe_audio(audio_uri)

        if not transcription_result.get("success", False):
            if transcription_result.get("error_code") == "no_speech_detected":
                return (
                    json.dumps(
                        {
                            "success": False,
                            "document_id": document_id,
                            "error": transcription_result.get("error"),
                            "error_code": "no_speech_detected",
                        }
                    ),
                    422,
                    {"Content-Type": "application/json"},
                )

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

        logger.info(f"Updating document {document_id} with transcription")
        update_result = update_document_content(document_id, transcript, token_auth)

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

        return (
            json.dumps(
                {
                    "success": True,
                    "document_id": document_id,
                    "message": "Transcription completed and document updated",
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        logger.error(f"Error in transcription endpoint: {str(e)}", exc_info=True)
        return (
            json.dumps({"success": False, "error": f"Internal error: {str(e)}"}),
            500,
            {"Content-Type": "application/json"},
        )
