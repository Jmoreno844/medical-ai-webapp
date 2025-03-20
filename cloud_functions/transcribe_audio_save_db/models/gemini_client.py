"""
Module for handling Gemini model initialization and interaction.
"""

import os
import logging
from typing import Dict, Any, Optional
import google.auth
import time

import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel, Part

from config import is_production, GENERATION_CONFIG

# Initialize logger
logger = logging.getLogger(__name__)

# Global variables to maintain state across invocations
_vertexai_initialized = False
_model_instance = None
_current_model_name = None


def initialize_vertexai(project_id=None, location=None):
    """Initialize the Vertex AI Python SDK with appropriate credentials."""
    global _vertexai_initialized

    if not _vertexai_initialized:
        # Get project and location from environment variables if not provided
        project_id = project_id or os.environ.get("PROJECT_ID")
        location = location or os.environ.get("LOCATION")

        if not project_id or not location:
            raise ValueError(
                "PROJECT_ID and LOCATION must be set in environment variables"
            )

        if is_production():
            # In production, use the service account attached to the Cloud Function
            logger.info(
                "Production environment: Using service account attached to Cloud Function"
            )
            try:
                # google.auth.default() automatically detects and uses the attached service account
                credentials, detected_project = google.auth.default()
                logger.info(
                    f"Successfully obtained default credentials for project: {detected_project}"
                )

                # Initialize Vertex AI with default credentials
                vertexai.init(
                    project=project_id, location=location, credentials=credentials
                )
                _vertexai_initialized = True
                logger.info(
                    "Vertex AI initialized successfully with default credentials"
                )
            except Exception as e:
                logger.error(f"Error using default credentials: {str(e)}")
                raise
        else:
            # In local/test environment, use file-based credentials if specified
            credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

            if credentials_path:
                if not os.path.exists(credentials_path):
                    logger.warning(
                        f"Service account credentials file not found at {credentials_path}"
                    )
                logger.info(f"Using credentials from file: {credentials_path}")
            else:
                logger.warning(
                    "GOOGLE_APPLICATION_CREDENTIALS environment variable not set"
                )

            # Initialize Vertex AI (will use ADC or file-based credentials)
            vertexai.init(project=project_id, location=location)
            _vertexai_initialized = True
            logger.info("Vertex AI initialized successfully")


def get_gemini_model(model_name=None):
    """Get or create a Gemini model instance."""
    global _model_instance, _current_model_name

    # Use environment variable if not provided, with default fallback
    model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    # Initialize Vertex AI if needed
    initialize_vertexai()

    # Create new model instance if needed
    if _model_instance is None or _current_model_name != model_name:
        logger.info(f"Creating new Gemini model instance: {model_name}")
        _model_instance = GenerativeModel(model_name)
        _current_model_name = model_name

    return _model_instance


def create_generation_config():
    """Create a generation configuration with fixed settings."""
    return GenerationConfig(**GENERATION_CONFIG)


def generate_content(
    prompt: str,
    model_name: Optional[str] = None,
    additional_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate content using Gemini model, with support for audio and other content types.

    Args:
        prompt: Text prompt for content generation
        model_name: The Gemini model to use
        additional_params: Additional parameters like audio_uri

    Returns:
        Dictionary containing generated text and metadata
    """
    try:
        # Get model
        model = get_gemini_model(model_name)

        # Create generation config
        config = create_generation_config()

        logger.info("Sending request to Gemini API - starting to wait for response")
        start_time = time.time()

        # Prepare contents list for the model
        contents = []

        # Handle audio if provided - properly handle gs:// URI format
        if additional_params and "audio_uri" in additional_params:
            audio_uri = additional_params.get("audio_uri")
            mime_type = additional_params.get("mime_type", "audio/mpeg")

            # Ensure audio URI is in gs:// format if it's not already
            if not audio_uri.startswith("gs://") and "/" in audio_uri:
                from services.transcription import extract_gs_uri

                audio_uri = extract_gs_uri(audio_uri)

            logger.info(f"Adding audio from URI: {audio_uri}")
            audio_part = Part.from_uri(uri=audio_uri, mime_type=mime_type)
            contents.append(audio_part)

        # Add the text prompt
        contents.append(prompt)

        # Generate content with the model
        response = model.generate_content(
            contents,
            generation_config=config,
        )

        end_time = time.time()
        logger.info(
            f"Received response from Gemini API after {end_time - start_time:.2f} seconds"
        )

        # Extract usage data safely - completely reworked to avoid the error
        result = {
            "success": True,
            "text": response.text,
            "model": _current_model_name,
            "process_time_seconds": round(end_time - start_time, 2),
        }

        # Only add usage data if it's available
        try:
            if hasattr(response, "usage_metadata"):
                result["usage"] = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "candidates_token_count": response.usage_metadata.candidates_token_count,
                    "total_token_count": response.usage_metadata.total_token_count,
                }
            else:
                result["usage"] = {"available": False}
        except Exception as usage_error:
            logger.warning(f"Error extracting usage metadata: {str(usage_error)}")
            result["usage"] = {"error": str(usage_error)}

        return result

    except TimeoutError as e:
        logger.error(f"Timeout error when calling Gemini API: {str(e)}")
        return {
            "success": False,
            "error": "Request to Gemini API timed out. Please try again later.",
            "model": _current_model_name,
        }
    except Exception as e:
        logger.error(f"Error generating content: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e), "model": _current_model_name}
