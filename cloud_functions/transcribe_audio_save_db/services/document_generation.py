"""
Service for text summarization using the Gemini model.
"""

import logging
from typing import Dict, Any, Optional
import time
from config import SUMMARY_PROMPT, EXPAND_PROMPT, TRANSLATE_PROMPT
from models.gemini_client import (
    generate_content,
    generate_content_streaming as gemini_generate_content_streaming,
)
from services.django_api import send_generation_chunk

# Initialize logger
logger = logging.getLogger(__name__)

# Add a global variable for the document generation prompt at the top of the file
DOCUMENT_GENERATION_PROMPT = """
Tu tarea es generar un documento médico basado en los siguientes componentes:

1. PLANTILLA: 
{template}

2. CONTEXTO DEL PACIENTE:
{context}

3. TRANSCRIPCIÓN DE LA CONVERSACIÓN:
{transcription}

Instrucciones:
- Utiliza la estructura proporcionada en la PLANTILLA.
- Completa cada sección con información relevante del CONTEXTO y la TRANSCRIPCIÓN.
- Mantén un tono profesional y médico en todo momento.
- Si hay secciones en la plantilla que no pueden ser completadas con la información disponible, 
  indícalo con "Información no disponible" o proporciona una observación genérica apropiada.
- Asegúrate de que el documento final sea coherente y siga las convenciones médicas.
- Incluye fechas, horas y cualquier dato específico mencionado en la transcripción.
- No inventes información que no esté presente en los datos proporcionados.

Genera el documento completo:
"""


def summarize_text(text: str, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Summarize the provided text using the Gemini model.

    Args:
        text: The text to summarize
        model_name: Optional override for the Gemini model

    Returns:
        Dictionary containing generated summary and metadata
    """
    try:
        # Check if text is empty or too short
        if not text or len(text.strip()) < 10:
            return {
                "success": False,
                "error": "Text is too short for summarization",
                "model": model_name or "not_used",
            }

        # Format the prompt with the input text
        prompt = SUMMARY_PROMPT.format(text=text)

        # Use gemini client to generate content
        result = generate_content(prompt, model_name)

        # Log the raw result in case of issues
        logger.debug(f"Raw generate_content result: {result}")

        # Rename the response field from "text" to "summary" if successful
        if result.get("success", False) and "text" in result:
            result["summary"] = result.pop("text")

        return result

    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Summarization error: {str(e)}"}


def get_prompt_for_type(
    generation_type: str, content: str, custom_prompt: Optional[str] = None
) -> str:
    """
    Get the appropriate prompt template for the given generation type.

    Args:
        generation_type: Type of generation (summarize, expand, translate)
        content: The content to process
        custom_prompt: Optional custom prompt to use instead of templates

    Returns:
        Formatted prompt string
    """
    if custom_prompt and isinstance(custom_prompt, str):
        # Use custom prompt and substitute {text} with content
        return custom_prompt.replace("{text}", content)
    elif custom_prompt and not isinstance(custom_prompt, str):
        # Log warning if custom_prompt is not a string
        logger.warning(
            f"Custom prompt is not a string: {type(custom_prompt)}. Using default prompt instead."
        )

    # Use predefined templates based on type
    if generation_type == "summarize":
        return SUMMARY_PROMPT.format(text=content)
    elif generation_type == "expand":
        return EXPAND_PROMPT.format(text=content)
    elif generation_type == "translate":
        return TRANSLATE_PROMPT.format(text=content)
    else:
        # Default to summary if unknown type
        logger.warning(f"Unknown generation type: {generation_type}, using summarize")
        return SUMMARY_PROMPT.format(text=content)


def generate_content_streaming(
    content: str,
    generation_type: str = "summarize",
    custom_prompt: Optional[str] = None,
    id_documento: Optional[int] = None,  # Changed from document_id
    id_proceso: Optional[str] = None,  # Changed from processing_id
    token_auth: Optional[str] = None,  # Changed from auth_token
    model_name: Optional[str] = None,
    chunk_size: int = 50,  # Characters per chunk
    max_delay: float = 1.0,  # Maximum seconds between sending chunks
) -> Dict[str, Any]:
    """
    Generate content with streaming updates.

    Args:
        content: The content to process
        generation_type: Type of generation (summarize, expand, translate)
        custom_prompt: Optional custom prompt
        id_documento: ID of the document (for notifications)
        id_proceso: ID of the processing job (for notifications)
        token_auth: Auth token for Django API
        model_name: Optional model override
        chunk_size: Minimum characters per chunk
        max_delay: Maximum seconds between sending chunks

    Returns:
        Dictionary with generation results
    """
    try:
        # Check if input content is empty or too short
        if not content or len(content.strip()) < 10:
            error_msg = "Text is too short for processing"
            logger.warning(error_msg)

            # Send error notification if id_documento is provided
            if id_documento and id_proceso and token_auth:
                send_generation_chunk(
                    id_documento=id_documento,
                    id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                    chunk=None,
                    is_complete=False,
                    is_error=True,
                    error=error_msg,
                    token_auth=token_auth,
                )

            return {
                "success": False,
                "error": error_msg,
                "model": model_name or "not_used",
            }

        # Format the prompt based on generation type
        prompt = get_prompt_for_type(generation_type, content, custom_prompt)

        # Variables for streaming management
        buffer = ""
        last_sent_time = time.time()
        complete_text = ""

        # Define callback for streaming
        def process_chunk(chunk):
            nonlocal buffer, last_sent_time, complete_text

            # Add chunk to buffer and complete text
            buffer += chunk
            complete_text += chunk
            current_time = time.time()

            # Send if buffer is large enough or max delay exceeded
            if (
                len(buffer) >= chunk_size
                or (current_time - last_sent_time) >= max_delay
            ):
                # Send chunk if notifications are enabled
                if id_documento and id_proceso and token_auth:
                    send_generation_chunk(
                        id_documento=id_documento,
                        id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                        chunk=buffer,
                        is_complete=False,
                        is_error=False,
                        token_auth=token_auth,
                    )

                # Reset buffer and update timestamp
                buffer = ""
                last_sent_time = current_time

                # Log progress
                logger.debug(f"Sent chunk ({len(chunk)} chars) for job {id_proceso}")

            return True  # Continue streaming

        # Use Gemini client for streaming generation - FIXED HERE
        result = gemini_generate_content_streaming(prompt, model_name, process_chunk)

        # Check if generation was successful
        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error in AI model")
            logger.error(f"Streaming generation failed: {error_msg}")

            # Send error notification
            if id_documento and id_proceso and token_auth:
                send_generation_chunk(
                    id_documento=id_documento,
                    id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                    chunk=None,
                    is_complete=False,
                    is_error=True,
                    error=error_msg,
                    token_auth=token_auth,
                )

            return result

        # Send any remaining buffered content
        if buffer and id_documento and id_proceso and token_auth:
            send_generation_chunk(
                id_documento=id_documento,
                id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                chunk=buffer,
                is_complete=False,
                is_error=False,
                token_auth=token_auth,
            )

        # Send final completion notification with full text
        if id_documento and id_proceso and token_auth:
            send_generation_chunk(
                id_documento=id_documento,
                id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                chunk=complete_text,
                is_complete=True,
                is_error=False,
                token_auth=token_auth,
            )

        # Return success with complete text
        return {
            "success": True,
            "text": complete_text,
            "model": result.get("model", "unknown"),
        }

    except Exception as e:
        error_msg = f"Error generating content: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Send error notification
        if id_documento and id_proceso and token_auth:
            send_generation_chunk(
                id_documento=id_documento,
                id_proceso=id_proceso,  # FIXED: changed from processing_id to id_proceso
                chunk=None,
                is_complete=False,
                is_error=True,
                error=error_msg,
                token_auth=token_auth,
            )

        return {"success": False, "error": error_msg}


def generate_document_from_components(
    template_content: str,
    context_content: str,
    transcription_content: str,
    id_documento_nuevo: int,  # Standardized parameter name
    id_proceso: str,
    auth_token: str,
    model_name: str = None,
) -> Dict[str, Any]:
    """
    Generate a document by combining template, context and transcription content.

    Args:
        template_content: The template structure to use
        context_content: Context information about the patient/encounter (can be empty)
        transcription_content: Transcription of the doctor-patient conversation
        id_documento_nuevo: ID of the document to update
        id_proceso: ID of the processing job
        auth_token: Auth token for Django API
        model_name: Optional model name override

    Returns:
        Dictionary with generation results
    """
    try:
        # Validate template and transcription inputs with descriptive errors
        if not template_content or len(template_content.strip()) < 10:
            error_msg = (
                "Template content is too short or empty (min 10 characters required)"
            )
            logger.error(error_msg)

            # Notify clients of the error
            send_generation_chunk(
                id_documento=id_documento_nuevo,
                id_proceso=id_proceso,  # Parameter name is already correct here
                chunk=None,
                is_complete=False,
                is_error=True,
                error=error_msg,
                token_auth=auth_token,
            )
            return {"success": False, "error": error_msg}

        # Context can be empty - if it is, use a default message
        if not context_content or len(context_content.strip()) < 1:
            logger.info("Context content is empty, using default message")
            context_content = "No se agregó contexto."

        if not transcription_content or len(transcription_content.strip()) < 10:
            error_msg = "Transcription content is too short or empty (min 10 characters required)"
            logger.error(error_msg)

            # Notify clients of the error
            send_generation_chunk(
                id_documento=id_documento_nuevo,
                id_proceso=id_proceso,  # Parameter name is already correct here
                chunk=None,
                is_complete=False,
                is_error=True,
                error=error_msg,
                token_auth=auth_token,
            )
            return {"success": False, "error": error_msg}

        # Log content sizes before proceeding
        logger.info(
            f"Document generation input sizes - Template: {len(template_content)} chars, "
            f"Context: {len(context_content)} chars, "
            f"Transcription: {len(transcription_content)} chars"
        )

        # Format the prompt with all components
        prompt = DOCUMENT_GENERATION_PROMPT.format(
            template=template_content,
            context=context_content,
            transcription=transcription_content,
        )

        # Variables for streaming management
        buffer = ""
        last_sent_time = time.time()
        complete_text = ""
        chunk_size = 50  # Characters per chunk
        max_delay = 1.0  # Maximum seconds between chunks

        # Define callback for streaming
        def process_chunk(chunk):
            nonlocal buffer, last_sent_time, complete_text

            # Add chunk to buffer and complete text
            buffer += chunk
            complete_text += chunk
            current_time = time.time()

            # Send if buffer is large enough or max delay exceeded
            if (
                len(buffer) >= chunk_size
                or (current_time - last_sent_time) >= max_delay
            ):
                # Send chunk
                send_generation_chunk(
                    id_documento=id_documento_nuevo,  # Use id_documento_nuevo consistently
                    id_proceso=id_proceso,
                    chunk=buffer,
                    is_complete=False,
                    is_error=False,
                    token_auth=auth_token,
                )

                # Reset buffer and update timestamp
                buffer = ""
                last_sent_time = current_time

                # Log progress
                logger.debug(
                    f"Sent document chunk ({len(chunk)} chars) for job {id_proceso}"
                )

            return True  # Continue streaming

        # Use Gemini client for streaming generation - FIXED HERE
        logger.info(
            f"Starting document generation with prompt of {len(prompt)} characters"
        )
        result = gemini_generate_content_streaming(prompt, model_name, process_chunk)

        # Check if generation was successful
        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error in AI model")
            logger.error(f"Document generation failed: {error_msg}")
            return result

        # Send any remaining buffered content
        if buffer:
            send_generation_chunk(
                id_documento=id_documento_nuevo,
                id_proceso=id_proceso,
                chunk=buffer,
                is_complete=False,
                is_error=False,
                token_auth=auth_token,
            )

        # Send final completion notification with full text
        send_generation_chunk(
            id_documento=id_documento_nuevo,
            id_proceso=id_proceso,
            chunk=complete_text,
            is_complete=True,
            is_error=False,
            token_auth=auth_token,
        )

        # Return success with complete text
        return {
            "success": True,
            "text": complete_text,
            "model": result.get("model", "unknown"),
        }

    except Exception as e:
        error_msg = f"Error generating document: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}
