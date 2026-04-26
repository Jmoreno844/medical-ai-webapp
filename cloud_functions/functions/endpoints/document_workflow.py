"""
Cloud Function endpoint for complete document generation workflow.
"""

import json
import logging

from langsmith_tracing import trace_operation

from services.document_generation.generator import generate_document_from_components
from services.backend_api import send_generation_chunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _langsmith_request_inputs(request) -> dict:
    request_json = request.get_json(silent=True) or {}
    context_document = request_json.get("context_document", {}) or {}
    transcription_document = request_json.get("transcription_document", {}) or {}
    template = request_json.get("template", {}) or {}
    return {
        "method": request.method,
        "new_document_id": request_json.get("new_document_id"),
        "process_id": request_json.get("process_id"),
        "validate_only": bool(request_json.get("validate_only", False)),
        "context_length": len(context_document.get("content") or ""),
        "transcription_length": len(transcription_document.get("content") or ""),
        "template_length": len(template.get("content") or ""),
        "has_auth_token": bool(request_json.get("auth_token")),
    }


def _langsmith_request_outputs(response: tuple) -> dict:
    body, status_code, _headers = response
    payload = json.loads(body)
    return {
        "status_code": status_code,
        "success": bool(payload.get("success")),
        "document_id": payload.get("document_id"),
        "process_id": payload.get("process_id"),
        "validate_only": bool(payload.get("validate_only", False)),
    }


def generate_document_workflow(request) -> tuple:
    """
    Cloud Function to generate a document by combining template, context and transcription.

    Expects JSON:
        - new_document_id: ID of the new document to update
        - process_id: ID of the generation job
        - context_document: { id, content }
        - transcription_document: { id, content }
        - template: { id, content }
        - auth_token: Bearer JWT for Django callbacks
        - validate_only: bool
    """
    from tracing import configure_tracing, run_with_request_span

    configure_tracing()
    return run_with_request_span(
        request,
        "cloud_functions.document_generation",
        _generate_document_workflow_impl,
    )


@trace_operation(
    name="cloud_functions.document_generation_request",
    run_type="chain",
    process_inputs=_langsmith_request_inputs,
    process_outputs=_langsmith_request_outputs,
    tags=["document_generation", "http"],
)
def _generate_document_workflow_impl(request) -> tuple:
    logger.info(f"Received document generation workflow request: {request.method}")

    try:
        request_json = request.get_json(silent=True) or {}
        logger.info(f"Request parameters: {list(request_json.keys())}")
    except Exception as e:
        logger.warning(f"Could not log request parameters: {str(e)}")

    if request.method != "POST":
        return (
            json.dumps({"success": False, "error": "Only POST method is allowed"}),
            405,
            {"Content-Type": "application/json"},
        )

    try:
        request_json = request.get_json(silent=True) or {}

        validate_only = request_json.get("validate_only", False)
        if validate_only:
            logger.info("Running in validation-only mode")

        new_document_id = request_json.get("new_document_id")
        logger.info(f"Received new_document_id={new_document_id}")

        process_id = request_json.get("process_id")
        context_document = request_json.get("context_document", {})
        transcription_document = request_json.get("transcription_document", {})
        template = request_json.get("template", {})
        token_auth = request_json.get("auth_token")

        if not new_document_id:
            logger.error("Missing new_document_id parameter")
            return (
                json.dumps(
                    {"success": False, "error": "Missing new_document_id parameter"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        try:
            new_document_id = int(new_document_id)
            if new_document_id <= 0:
                return (
                    json.dumps(
                        {
                            "success": False,
                            "error": "new_document_id must be a positive integer",
                        }
                    ),
                    400,
                    {"Content-Type": "application/json"},
                )
        except ValueError:
            return (
                json.dumps(
                    {"success": False, "error": "new_document_id must be an integer"}
                ),
                400,
                {"Content-Type": "application/json"},
            )

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("document_id", new_document_id)
                span.set_attribute("validate_only", bool(validate_only))
        except Exception:
            pass

        if not process_id:
            return (
                json.dumps({"success": False, "error": "Missing process_id parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        if not token_auth:
            return (
                json.dumps({"success": False, "error": "Missing auth_token parameter"}),
                400,
                {"Content-Type": "application/json"},
            )

        context_content = context_document.get("content", "")
        if not context_content or not context_content.strip():
            logger.info("Context document is empty, will use default message")
            context_content = "No se agregó contexto."
            context_document["content"] = context_content

        transcription_content = transcription_document.get("content")
        if not transcription_content or not transcription_content.strip():
            logger.error("Missing or empty transcription_document content")
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": "Missing transcription_document content",
                    }
                ),
                400,
                {"Content-Type": "application/json"},
            )

        template_content = template.get("content")
        if not template_content or not template_content.strip():
            logger.error("Missing or empty template content")
            return (
                json.dumps({"success": False, "error": "Missing template content"}),
                400,
                {"Content-Type": "application/json"},
            )

        logger.info(
            f"Content lengths - Context: {len(context_content)}, "
            f"Transcription: {len(transcription_content)}, "
            f"Template: {len(template_content)}"
        )

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

        logger.info(
            f"Starting document generation for document {new_document_id}, job {process_id}"
        )

        try:
            resultado = generate_document_from_components(
                template_content=template_content,
                context_content=context_content,
                transcription_content=transcription_document.get("content"),
                new_document_id=new_document_id,
                process_id=process_id,
                auth_token=token_auth,
            )

            if not resultado.get("success", False):
                error_msg = resultado.get(
                    "error", "Unknown error during document generation"
                )
                logger.error(f"Document generation failed: {error_msg}")

                send_generation_chunk(
                    document_id=new_document_id,
                    process_id=process_id,
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

            return (
                json.dumps(
                    {
                        "success": True,
                        "document_id": new_document_id,
                        "process_id": process_id,
                        "message": "Document generation completed successfully",
                    }
                ),
                200,
                {"Content-Type": "application/json"},
            )

        except Exception as e:
            logger.error(f"Error during document generation: {str(e)}", exc_info=True)

            send_generation_chunk(
                document_id=new_document_id,
                process_id=process_id,
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
