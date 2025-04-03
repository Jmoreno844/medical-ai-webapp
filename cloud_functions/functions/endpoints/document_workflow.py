"""
Cloud Function endpoint for complete document generation workflow.
"""

import logging
import json
import functions_framework
from services.document_generation.generator import generate_document_from_components
from services.django_api import send_generation_chunk

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                transcription_content=documento_transcripcion.get("content"),
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
