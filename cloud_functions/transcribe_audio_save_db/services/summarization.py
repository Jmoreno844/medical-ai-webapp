"""
Service for text summarization using the Gemini model.
"""

import logging
from typing import Dict, Any, Optional

from config import SUMMARY_PROMPT
from models.gemini_client import generate_content

# Initialize logger
logger = logging.getLogger(__name__)


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
