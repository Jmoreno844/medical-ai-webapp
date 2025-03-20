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


def update_document_content(
    document_id: int, content: str, auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update a document's content in the Django API.

    Args:
        document_id: The ID of the document to update
        content: The new content (summary) to save
        auth_token: Authentication token for the Django API (overrides env var if provided)

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
    api_url = f"{base_url}/documento_by_function/{document_id}"

    # More detailed debugging for auth token
    if auth_token:
        logger.info(
            f"Received auth token in update_document_content (length: {len(auth_token)})"
        )
        # Check if token looks like JWT (format: xxx.yyy.zzz)
        if "." in auth_token and len(auth_token.split(".")) == 3:
            logger.info("Token appears to be in JWT format")
        else:
            logger.warning(
                "Token doesn't appear to be in standard JWT format (xxx.yyy.zzz)"
            )
    else:
        logger.warning("No auth token provided to update_document_content function")
        auth_token = get_api_auth_token()
        if auth_token:
            logger.info("Using fallback token from environment")
        else:
            logger.error(
                "⚠️ No auth token available from any source - request will likely fail"
            )

    # Prepare headers with improved token handling
    headers = {
        "Content-Type": "application/json",
    }

    # Improved token handling logic
    if auth_token:
        # For JWT tokens, always use Bearer format
        if "." in auth_token and len(auth_token.split(".")) == 3:
            if not auth_token.startswith("Bearer "):
                headers["Authorization"] = f"Bearer {auth_token}"
                logger.info("Added 'Bearer' prefix to JWT token")
            else:
                headers["Authorization"] = auth_token
                logger.info("Using JWT token with existing Bearer prefix")
        else:
            # For non-JWT tokens, use as-is
            headers["Authorization"] = auth_token
            logger.info("Using non-JWT token as-is")

        logger.info(
            f"Final Authorization header: {headers.get('Authorization', '')[:15]}..."
        )
    else:
        logger.error("⚠️ No authorization header will be sent - expect 401 Unauthorized")

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

        # Try to get status code and response details
        status_code = None
        response_text = None
        if hasattr(e, "response"):
            status_code = getattr(e.response, "status_code", None)
            try:
                response_text = e.response.text
            except:
                pass

        # Provide more helpful error info for authentication errors
        if status_code == 401:
            logger.error(
                "🔐 Authentication failed (401 Unauthorized) - Check your token!"
            )
            if auth_token:
                logger.error(f"Token used (first 10 chars): {auth_token[:10]}...")
            if response_text:
                logger.error(f"Response from server: {response_text}")

            return {
                "success": False,
                "error": "Authentication failed - invalid or expired token",
                "status_code": 401,
                "details": response_text or "No error details available",
            }

        return {"success": False, "error": error_msg, "status_code": status_code}

    except Exception as e:
        error_msg = f"Unexpected error updating document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}
