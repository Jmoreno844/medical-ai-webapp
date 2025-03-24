"""
Cloud Functions for transcription and document generation.
"""

import logging
import json
import functions_framework
from typing import Dict, Any

from services.transcription import transcribe_audio
from services.document_generation import (
    summarize_text,
    generate_content_streaming,
    generate_document_from_components,
)
from services.django_api import update_document_content, send_generation_chunk

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


@functions_framework.http
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


@functions_framework.http
def document_streaming_generation(request) -> tuple:
    """
    Cloud Function to generate document content with streaming updates.

    Expects:
        - document_id: ID of the document to update
        - processing_id: ID of the generation job
        - generation_type: Type of generation to perform
        - content: Content to process (optional)
        - prompt: Custom prompt (optional)
        - auth_token: Auth token for Django API
    """
    # Log request details
    logger.info(f"Received streaming generation request: {request.method}")

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
        processing_id = request_json.get("processing_id")
        generation_type = request_json.get("generation_type", "summarize")
        content = request_json.get("content", "")
        prompt = request_json.get("prompt")
        auth_token = request_json.get("auth_token")

        # Validate required parameters
        if not document_id:
            return (
                json.dumps(
                    {"success": False, "error": "Missing document_id parameter"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        if not processing_id:
            return (
                json.dumps(
                    {"success": False, "error": "Missing processing_id parameter"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        if not content:
            return (
                json.dumps({"success": False, "error": "Missing content parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        if not auth_token:
            return (
                json.dumps({"success": False, "error": "Missing auth_token parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        # Acknowledge request immediately
        logger.info(
            f"Starting streaming generation for document {document_id}, job {processing_id}"
        )

        # Start streaming generation
        try:
            # Generate content with streaming
            result = generate_content_streaming(
                content=content,
                generation_type=generation_type,
                custom_prompt=prompt,
                document_id=document_id,
                processing_id=processing_id,
                auth_token=auth_token,
            )

            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error during generation")
                logger.error(f"Generation failed: {error_msg}")

                # Notify about error
                send_generation_chunk(
                    id_documento=document_id,
                    id_proceso=processing_id,
                    chunk=None,
                    is_complete=False,
                    is_error=True,
                    error=error_msg,
                    token_auth=auth_token,
                )

                return (
                    json.dumps({"success": False, "error": error_msg}),
                    500,
                    {"Content-Type": "application/json"},
                )

            # Return success response
            return (
                json.dumps(
                    {
                        "success": True,
                        "document_id": document_id,
                        "processing_id": processing_id,
                        "message": "Generation completed successfully",
                    }
                ),
                200,
                {"Content-Type": "application/json"},
            )

        except Exception as e:
            logger.error(f"Error during streaming generation: {str(e)}", exc_info=True)

            # Notify about error
            send_generation_chunk(
                id_documento=document_id,
                id_proceso=processing_id,
                chunk=None,
                is_complete=False,
                is_error=True,
                error=f"Error en la generación: {str(e)}",
                token_auth=auth_token,
            )

            return (
                json.dumps(
                    {"success": False, "error": f"Error during generation: {str(e)}"}
                ),
                500,
                {"Content-Type": "application/json"},
            )

    except Exception as e:
        logger.error(f"Error processing generation request: {str(e)}", exc_info=True)
        return (
            json.dumps({"success": False, "error": f"Internal server error: {str(e)}"}),
            500,
            {"Content-Type": "application/json"},
        )


@functions_framework.http
def generate_document_workflow(request) -> tuple:
    """
    Cloud Function to generate a document by combining:
    - Template structure (plantilla_doctor.contenido)
    - Context document content
    - Transcription content

    Expects:
        - id_documento_nuevo: ID of the new document to update
        - id_proceso: ID of the generation job
        - documento_contexto: Dict with context document id and content
        - documento_transcripcion: Dict with transcription document id and content
        - plantilla: Dict with template id and content
        - token_auth: Auth token for Django API
        - validate_only: Boolean flag to only validate inputs without generating
    """
    # Log request details
    logger.info(f"Received document generation workflow request: {request.method}")

    try:
        # Log request body for debugging
        request_json = request.get_json(silent=True) or {}
        logger.info(f"Request parameters: {list(request_json.keys())}")
    except Exception as e:
        logger.warning(f"Could not log request parameters: {str(e)}")

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

        # Check if this is validate_only mode
        validate_only = request_json.get("validate_only", False)
        if validate_only:
            logger.info("Running in validation-only mode")

        # Get the document ID parameter
        id_documento_nuevo = request_json.get("id_documento_nuevo")
        logger.info(f"Received id_documento_nuevo={id_documento_nuevo}")

        id_proceso = request_json.get("id_proceso")
        documento_contexto = request_json.get("documento_contexto", {})
        documento_transcripcion = request_json.get("documento_transcripcion", {})
        plantilla = request_json.get("plantilla", {})
        token_auth = request_json.get("auth_token")

        # Basic parameter validation
        if not id_documento_nuevo:
            logger.error("Missing id_documento_nuevo parameter")
            return (
                json.dumps(
                    {"success": False, "error": "Missing id_documento_nuevo parameter"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        # Validate document ID directly
        try:
            id_documento_nuevo = int(id_documento_nuevo)
            if id_documento_nuevo <= 0:
                return (
                    json.dumps(
                        {
                            "success": False,
                            "error": "id_documento_nuevo must be a positive integer",
                        }
                    ),
                    400,
                    {"Content-Type": "application/json"},
                )
        except ValueError:
            return (
                json.dumps(
                    {"success": False, "error": "id_documento_nuevo must be an integer"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        if not id_proceso:
            return (
                json.dumps({"success": False, "error": "Missing id_proceso parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        if not token_auth:
            return (
                json.dumps({"success": False, "error": "Missing auth_token parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        # Content validation - don't validate context content, but transcription content must exist
        context_content = documento_contexto.get("content", "")
        # If context is empty, we'll just use a default message, no need to return an error
        if not context_content or not context_content.strip():
            logger.info("Context document is empty, will use default message")
            context_content = "No se agregó contexto."
            # Update the context content in the request data
            documento_contexto["content"] = context_content

        transcription_content = documento_transcripcion.get("content")
        if not transcription_content or not transcription_content.strip():
            logger.error("Missing or empty documento_transcripcion content")
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": "Missing documento_transcripcion content",
                    }
                ),
                400,
                {"Content-Type": "application/json"},
            )

        # Get the template content
        template_content = plantilla.get("content")
        if not template_content or not template_content.strip():
            logger.error("Missing or empty plantilla content")
            return (
                json.dumps({"success": False, "error": "Missing plantilla content"}),
                400,
                {"Content-Type": "application/json"},
            )

        # Log content lengths for debugging
        logger.info(
            f"Content lengths - Context: {len(context_content)}, "
            f"Transcription: {len(transcription_content)}, "
            f"Template: {len(template_content)}"
        )

        # If validate_only, return success without generating
        if validate_only:
            logger.info(
                "Validation successful, skipping generation in validate-only mode"
            )
            return (
                json.dumps(
                    {
                        "success": True,
                        "message": "Validation successful, all inputs are valid",
                        "validate_only": True,
                    }
                ),
                200,
                {"Content-Type": "application/json"},
            )

        # If we get here, proceed with generation
        # Acknowledge request immediately
        logger.info(
            f"Starting document generation for document {id_documento_nuevo}, job {id_proceso}"
        )

        # Start document generation process
        try:
            # Generate document content with streaming
            resultado = generate_document_from_components(
                template_content=template_content,
                context_content=context_content,
                transcription_content=documento_transcripcion.get(
                    "content"
                ),  # Added missing argument
                id_documento_nuevo=id_documento_nuevo,
                id_proceso=id_proceso,
                auth_token=token_auth,
            )

            if not resultado.get("success", False):
                error_msg = resultado.get(
                    "error", "Unknown error during document generation"
                )
                logger.error(f"Document generation failed: {error_msg}")

                # Notify about error
                send_generation_chunk(
                    id_documento=id_documento_nuevo,
                    id_proceso=id_proceso,
                    chunk=None,
                    is_complete=False,
                    is_error=True,
                    error=error_msg,
                    token_auth=token_auth,
                )

                return (
                    json.dumps({"success": False, "error": error_msg}),
                    500,
                    {"Content-Type": "application/json"},
                )

            # Return success response
            return (
                json.dumps(
                    {
                        "success": True,
                        "document_id": id_documento_nuevo,
                        "id_proceso": id_proceso,
                        "message": "Document generation completed successfully",
                    }
                ),
                200,
                {"Content-Type": "application/json"},
            )

        except Exception as e:
            logger.error(f"Error during document generation: {str(e)}", exc_info=True)

            # Notify about error
            send_generation_chunk(
                id_documento=id_documento_nuevo,
                id_proceso=id_proceso,
                chunk=None,
                is_complete=False,
                is_error=True,
                error=f"Error en la generación del documento: {str(e)}",
                token_auth=token_auth,
            )

            return (
                json.dumps(
                    {
                        "success": False,
                        "error": f"Error during document generation: {str(e)}",
                    }
                ),
                500,
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
