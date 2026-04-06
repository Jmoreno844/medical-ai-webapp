"""
Client for Google's Gemini API using VertexAI
"""

import os
import logging
from typing import Dict, Any, Optional, Callable

import vertexai
from google.api_core.exceptions import GoogleAPIError
from vertexai.generative_models import GenerativeModel

from langsmith_tracing import trace_operation

# Configure logging
logger = logging.getLogger(__name__)

# Environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT")
LOCATION = os.environ.get("GCP_REGION", "us-central1")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-001")

# Initialization flag
_is_initialized = False


def _langsmith_generation_inputs(
    prompt: str,
    model_name: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "model": model_name or DEFAULT_MODEL,
        "prompt_length": len(prompt or ""),
    }


def _langsmith_generation_outputs(result: Dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "model": result.get("model"),
        "text_length": len(result.get("text") or ""),
        "error_present": bool(result.get("error")),
    }


def _langsmith_streaming_inputs(
    prompt: str,
    model_name: Optional[str] = None,
    chunk_handler: Optional[Callable[[str], bool]] = None,
) -> dict[str, Any]:
    return {
        "model": model_name or DEFAULT_MODEL,
        "prompt_length": len(prompt or ""),
        "has_chunk_handler": chunk_handler is not None,
    }


def initialize_vertexai():
    """Initialize the VertexAI library"""
    global _is_initialized

    if _is_initialized:
        logger.debug("VertexAI already initialized, skipping")
        return

    if not PROJECT_ID:
        error_msg = "GCP_PROJECT not found in environment variables"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        logger.info(
            f"Initializing VertexAI with project={PROJECT_ID}, location={LOCATION}"
        )
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        _is_initialized = True
    except Exception as e:
        logger.error(f"Failed to initialize VertexAI: {str(e)}")
        raise


def get_gemini_model(model_name: Optional[str] = None) -> GenerativeModel:
    """
    Get a Gemini model instance.

    Args:
        model_name: The name of the model to use

    Returns:
        GenerativeModel instance
    """
    if not _is_initialized:
        initialize_vertexai()

    model = model_name or DEFAULT_MODEL
    logger.info(f"Creating GenerativeModel with name: {model}")
    return GenerativeModel(model)


@trace_operation(
    name="cloud_functions.gemini_generate_content",
    run_type="llm",
    process_inputs=_langsmith_generation_inputs,
    process_outputs=_langsmith_generation_outputs,
    tags=["gemini", "content_generation"],
)
def generate_content(prompt: str, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate content using Gemini model.

    Args:
        prompt: The prompt to send to the model
        model_name: Optional model name override

    Returns:
        Dictionary with generation results
    """
    model_id = model_name or DEFAULT_MODEL

    try:
        # Make sure VertexAI is initialized
        if not _is_initialized:
            initialize_vertexai()

        logger.info(f"Generating content with model: {model_id}")

        # Initialize the model
        model = get_gemini_model(model_id)

        # Generate content
        response = model.generate_content(prompt)

        # Check if response has content
        if not response or not response.text:
            return {
                "success": False,
                "error": "Empty response from model",
                "model": model_id,
            }

        return {
            "success": True,
            "text": response.text,
            "model": model_id,
        }

    except GoogleAPIError as e:
        logger.error(f"Gemini API error: {str(e)}")
        return {
            "success": False,
            "error": f"Gemini API error: {str(e)}",
            "model": model_id,
        }
    except Exception as e:
        logger.error(f"Error generating content: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Generation error: {str(e)}",
            "model": model_id,
        }


@trace_operation(
    name="cloud_functions.gemini_generate_content_streaming",
    run_type="llm",
    process_inputs=_langsmith_streaming_inputs,
    process_outputs=_langsmith_generation_outputs,
    tags=["gemini", "streaming"],
)
def generate_content_streaming(
    prompt: str,
    model_name: Optional[str] = None,
    chunk_handler: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """
    Generate content using Gemini model with streaming.

    Args:
        prompt: The prompt to send to the model
        model_name: Optional model name override
        chunk_handler: Callback function for processing chunks

    Returns:
        Dictionary with generation results
    """
    model_id = model_name or DEFAULT_MODEL
    complete_response = ""

    try:
        # Make sure VertexAI is initialized
        if not _is_initialized:
            initialize_vertexai()

        logger.info(f"Generating content with streaming using model: {model_id}")

        # Initialize the model
        model = get_gemini_model(model_id)

        # Generate content with streaming
        stream = model.generate_content(prompt, stream=True)

        # Process the streaming response
        for response in stream:
            if not response.text:
                continue

            complete_response += response.text

            # If a handler is provided, call it with the chunk
            if chunk_handler:
                continue_streaming = chunk_handler(response.text)
                if not continue_streaming:
                    logger.info("Streaming stopped by handler")
                    break

        return {
            "success": True,
            "text": complete_response,
            "model": model_id,
        }

    except GoogleAPIError as e:
        logger.error(f"Gemini API error during streaming: {str(e)}")
        return {
            "success": False,
            "error": f"Gemini API error: {str(e)}",
            "model": model_id,
        }
    except Exception as e:
        logger.error(f"Error during streaming generation: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Streaming error: {str(e)}",
            "model": model_id,
        }
