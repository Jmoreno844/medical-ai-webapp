"""
Cloud Function endpoint for streaming document generation.
"""

import logging
import json
import functions_framework
from services.document_generation.generator import generate_content_streaming
from services.django_api import send_generation_chunk

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                id_documento=document_id,
                id_proceso=processing_id,
                token_auth=auth_token,
                model_name=None,
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
