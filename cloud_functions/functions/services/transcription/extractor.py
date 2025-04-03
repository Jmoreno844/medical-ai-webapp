"""
Utilities for extracting and validating audio URIs.
"""

import logging
import re

# Initialize logger
logger = logging.getLogger(__name__)


def extract_gs_uri(audio_uri: str) -> str:
    """
    Validate and ensure we have a proper gs:// URI format.

    Args:
        audio_uri: The URI for the audio file (could be gs:// URI or signed URL)

    Returns:
        GCS URI in gs:// format
    """
    # If it's already a gs:// URI, return it as is
    if audio_uri.startswith("gs://"):
        return audio_uri

    # Try to extract gs:// path from URL
    # Example: https://storage.googleapis.com/bucket-name/object-path -> gs://bucket-name/object-path
    storage_url_pattern = r"https://storage\.googleapis\.com/([^/]+)/(.*)"
    match = re.match(storage_url_pattern, audio_uri)

    if match:
        bucket = match.group(1)
        object_path = match.group(2)
        return f"gs://{bucket}/{object_path}"

    # If can't extract, log warning and return original
    logger.warning(f"Could not convert to gs:// format: {audio_uri}")
    return audio_uri
