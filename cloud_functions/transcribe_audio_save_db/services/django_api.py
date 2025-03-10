"""
Service for interacting with the Django API.
"""

import os
import requests
import logging
import json
from typing import Dict, Any, Optional
import time

# Initialize logger
logger = logging.getLogger(__name__)


def get_api_base_url():
    """Get the Django API base URL from environment variables."""
    api_base_url = os.environ.get("DJANGO_API_BASE_URL")
    if not api_base_url:
        default_url = "http://localhost:8000/api"
        logger.warning(f"DJANGO_API_BASE_URL not set, using default: {default_url}")
        return default_url
    return api_base_url


def get_api_auth_token():
    """Get the Django API authentication token from environment variables."""
    token = os.environ.get("DJANGO_API_AUTH_TOKEN")
    if token:
        logger.debug("Using authentication token from environment variables")
    else:
        logger.debug("No authentication token provided")
    return token


def update_document_content(document_id: int, content: str) -> Dict[str, Any]:
    """
    Update a document's content in the Django API.

    Args:
        document_id: The ID of the document to update
        content: The new content (summary) to save

    Returns:
        Dictionary containing the API response or error information
    """
    # Validate document_id
    try:
        document_id = int(document_id)
        if document_id <= 0:
            error_msg = (
                f"Invalid document_id: {document_id}. Must be a positive integer."
            )
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    except (TypeError, ValueError) as e:
        error_msg = f"Invalid document_id format: {document_id}. Error: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    base_url = get_api_base_url()
    api_url = f"{base_url}/documento/{document_id}"
    auth_token = get_api_auth_token()

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
    }

    # Add authorization if token is available
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
        logger.debug("Added authorization header")

    # Prepare payload
    payload = {"contenido": content}

    logger.info(f"Making API call to update document {document_id}")
    logger.info(f"API URL: {api_url}")

    try:
        # Measure API call time
        start_time = time.time()

        # Make the API request
        response = requests.patch(api_url, json=payload, headers=headers, timeout=30)

        end_time = time.time()
        duration = round(end_time - start_time, 2)

        logger.info(
            f"API response received in {duration} seconds with status code: {response.status_code}"
        )

        # Check if the request was successful
        response.raise_for_status()

        # Try to parse response as JSON
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            response_data = {"raw_response": response.text}

        logger.info(f"Document {document_id} updated successfully")
        return {
            "success": True,
            "status_code": response.status_code,
            "response": response_data,
            "duration_seconds": duration,
        }

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error while updating document {document_id}: {str(e)}"
        logger.error(
            f"{error_msg}. Check if Django server is running and accessible at {api_url}"
        )
        return {"success": False, "error": error_msg}

    except requests.exceptions.RequestException as e:
        error_msg = f"Error updating document {document_id}: {str(e)}"
        logger.error(error_msg)

        # Try to get status code if available
        status_code = (
            getattr(e.response, "status_code", None) if hasattr(e, "response") else None
        )

        return {"success": False, "error": error_msg, "status_code": status_code}

    except Exception as e:
        error_msg = f"Unexpected error updating document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}
