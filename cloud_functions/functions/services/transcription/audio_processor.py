"""
Service for processing and transcribing audio using Gemini.
"""

import logging
import os
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from vertexai.generative_models import GenerationConfig, Part

from config import TRANSCRIPTION_PROMPT
from langsmith_tracing import trace_operation
from models.gemini_client import initialize_vertexai, get_gemini_model
from services.transcription.extractor import extract_gs_uri

# Initialize logger
logger = logging.getLogger(__name__)

NO_SPEECH_SENTINEL = "NO_SPEECH_DETECTED"
_AUDIO_MIME_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


def _detect_audio_mime_type(audio_uri: str) -> str:
    """Infer the MIME type from the URI path when possible."""
    parsed = urlparse(audio_uri)
    _, extension = os.path.splitext(parsed.path.lower())
    return _AUDIO_MIME_TYPES.get(extension, "audio/mpeg")


def _normalize_transcript(raw_text: Optional[str]) -> Optional[str]:
    """Normalize model output and detect explicit no-speech responses."""
    if not raw_text:
        return None

    transcript = raw_text.strip()
    if not transcript:
        return None

    if transcript.upper() == NO_SPEECH_SENTINEL:
        return NO_SPEECH_SENTINEL

    return transcript


def _langsmith_transcribe_inputs(
    audio_uri: str,
    model_name: Optional[str] = None,
) -> dict[str, Any]:
    parsed = urlparse(str(audio_uri or ""))
    _, extension = os.path.splitext(parsed.path.lower())
    return {
        "audio_scheme": parsed.scheme or None,
        "audio_extension": extension or None,
        "model": model_name or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
    }


def _langsmith_transcribe_outputs(result: Dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "model": result.get("model"),
        "error_code": result.get("error_code"),
        "transcript_length": len(result.get("transcript") or ""),
    }


@trace_operation(
    name="cloud_functions.transcribe_audio",
    run_type="tool",
    process_inputs=_langsmith_transcribe_inputs,
    process_outputs=_langsmith_transcribe_outputs,
    tags=["transcription", "gemini"],
)
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

        mime_type = _detect_audio_mime_type(gcs_uri)
        logger.info(f"Creating audio part from URI: {gcs_uri} with mime_type={mime_type}")
        audio_part = Part.from_uri(uri=gcs_uri, mime_type=mime_type)

        # Create text prompt part
        text_prompt = TRANSCRIPTION_PROMPT

        # Combine parts for the model
        contents = [audio_part, text_prompt]

        # Generate content with the model
        logger.info("Sending request to Gemini for audio transcription")
        response = model.generate_content(
            contents,
            generation_config=GenerationConfig(
                temperature=0.0,
                top_p=0.1,
                candidate_count=1,
                max_output_tokens=2048,
            ),
        )

        # Extract text from response
        transcript = _normalize_transcript(getattr(response, "text", None))

        if transcript == NO_SPEECH_SENTINEL:
            logger.warning("Audio transcription skipped because no intelligible speech was detected")
            return {
                "success": False,
                "error": "No intelligible speech detected in the audio",
                "error_code": "no_speech_detected",
                "model": model_name,
            }

        if not transcript:
            logger.warning("Audio transcription returned an empty response")
            return {
                "success": False,
                "error": "Empty transcription response from model",
                "error_code": "empty_transcription",
                "model": model_name,
            }

        logger.info("Successfully received transcription response")
        return {
            "success": True,
            "transcript": transcript,
            "model": model_name,
        }

    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Transcription error: {str(e)}"}
