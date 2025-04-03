"""
Service for processing and transcribing audio using Gemini.
"""

import logging
from typing import Dict, Any, Optional
import os
from vertexai.generative_models import Part
from models.gemini_client import initialize_vertexai, get_gemini_model
from services.transcription.extractor import extract_gs_uri
from config import TRANSCRIPTION_PROMPT

# Initialize logger
logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_uri: str, model_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transcribe audio using the Gemini model.

    Args:
        audio_uri: The gs:// URI or URL for the audio file
        model_name: Optional override for the Gemini model

    Returns:
        Dictionary containing generated transcript and metadata
    """
    try:
        # Check if audio_uri is provided
        if not audio_uri:
            raise ValueError("Missing required parameter: audio_uri must be provided")

        logger.info(f"Using audio URL: {audio_uri}")

        # Ensure we have a valid gs:// URI
        gcs_uri = extract_gs_uri(audio_uri)

        # Get model name from environment or use provided model
        model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

        # Initialize Vertex AI before creating model instance
        initialize_vertexai()

        # Create model instance
        model = get_gemini_model(model_name)
        logger.info(f"Using model: {model_name}")

        # Create audio part from URI - use audio/mpeg to match the API response
        logger.info(f"Creating audio part from URI: {gcs_uri}")
        audio_part = Part.from_uri(uri=gcs_uri, mime_type="audio/mpeg")

        # Create text prompt part
        text_prompt = TRANSCRIPTION_PROMPT

        # Combine parts for the model
        contents = [audio_part, text_prompt]

        # Generate content with the model
        logger.info("Sending request to Gemini for audio transcription")
        response = model.generate_content(contents)

        # Extract text from response
        transcript = response.text

        logger.info("Successfully received transcription response")
        return {
            "success": True,
            "transcript": transcript,
            "model": model_name,
        }

    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Transcription error: {str(e)}"}
