import json
import logging
import requests
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Default URL for the Cloud Function
DEFAULT_CLOUD_FUNCTION_URL = (
    "https://us-central1-nodal-wall-426818-t6.cloudfunctions.net/gemini_handler"
)


def get_cloud_function_url() -> str:
    """
    Get the Cloud Function URL from settings or use default.

    Returns:
        The URL of the Gemini Cloud Function
    """
    return getattr(settings, "GEMINI_CLOUD_FUNCTION_URL", DEFAULT_CLOUD_FUNCTION_URL)


def generate_content(
    prompt: str,
    model_name: Optional[str] = None,
    generation_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate content using Gemini model via Cloud Function.

    Args:
        prompt: Text prompt for content generation
        model_name: The Gemini model to use (optional)
        generation_config: Dictionary of generation parameters (optional)

    Returns:
        Dictionary containing generated text and metadata

    Raises:
        ConnectionError: If unable to connect to the Cloud Function
        ValueError: If the Cloud Function returns an error
    """
    cloud_function_url = get_cloud_function_url()

    # Prepare the request payload
    payload = {"prompt": prompt}

    # Add optional parameters if provided
    if model_name:
        payload["model"] = model_name

    if generation_config:
        payload["generation_config"] = generation_config

    try:
        # Make the request to the Cloud Function
        response = requests.post(
            cloud_function_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,  # Long timeout for complex generation tasks
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse and return the response
        result = response.json()

        if not result.get("success", False):
            raise ValueError(
                f"Cloud Function error: {result.get('error', 'Unknown error')}"
            )

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to Gemini Cloud Function: {str(e)}")
        raise ConnectionError(f"Failed to connect to Gemini Cloud Function: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from Cloud Function: {str(e)}")
        raise ValueError(f"Invalid response from Gemini Cloud Function: {str(e)}")
