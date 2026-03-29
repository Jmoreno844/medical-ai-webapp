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


def build_django_request_headers(
    token_auth: Optional[str] = None, json_body: bool = True
) -> Dict[str, str]:
    """
    Build HTTP headers for Django API calls.
    JWTs (three dot-separated segments) get Authorization: Bearer <token>.
    """
    headers: Dict[str, str] = {}
    if json_body:
        headers["Content-Type"] = "application/json"
    if not token_auth:
        return headers
    raw = str(token_auth).strip()
    if raw.startswith("Bearer "):
        headers["Authorization"] = raw
    elif "." in raw and len(raw.split(".")) == 3:
        headers["Authorization"] = f"Bearer {raw}"
    else:
        headers["Authorization"] = raw
    return headers


def get_api_base_url():
    """Get the Django API base URL from environment variables."""
    api_base_url = os.environ.get("DJANGO_API_BASE_URL")
    if not api_base_url:
        # Default still includes /api for backward compatibility
        default_url = "http://localhost:8000/api"
        logger.warning(f"DJANGO_API_BASE_URL not set, using default: {default_url}")
        return default_url

    # Ensure the URL doesn't end with a slash before adding /api
    if api_base_url.endswith("/"):
        api_base_url = api_base_url[:-1]

    # Add /api to the base URL
    return f"{api_base_url}/api"


def notify_transcription_complete(
    id_documento: int, token_auth: Optional[str] = None
) -> Dict[str, Any]:
    """
    Notify Django that transcription is complete.

    Args:
        id_documento: The ID of the document that was transcribed
        token_auth: Authentication token for the Django API

    Returns:
        Dictionary containing the API response or error information
    """
    base_url = get_api_base_url()
    api_url = f"{base_url}/notify/transcription-complete"

    # Get auth token from parameter or environment
    if not token_auth:
        logger.debug("No authentication token provided")

    headers = build_django_request_headers(token_auth)

    # Prepare payload
    payload = {
        "id_documento": id_documento,  # Changed from documento_id
        "status": "complete",
    }

    logger.info(f"Notifying transcription completion for document {id_documento}")

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        logger.info(
            f"Successfully notified about document {id_documento} transcription completion"
        )
        return {
            "success": True,
            "status_code": response.status_code,
            "response": response.json() if response.text else {},
        }
    except Exception as e:
        logger.error(f"Error notifying transcription completion: {str(e)}")
        return {"success": False, "error": str(e)}


def update_document_content(
    id_documento: int, content: str, token_auth: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update a document's content in the Django API.

    Args:
        id_documento: The ID of the document to update
        content: The new content (summary) to save
        token_auth: Authentication token for the Django API (overrides env var if provided)

    Returns:
        Dictionary containing the API response or error information
    """
    # Validate id_documento
    try:
        id_documento = int(id_documento)
        if id_documento <= 0:
            error_msg = (
                f"Invalid id_documento: {id_documento}. Must be a positive integer."
            )
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    except (TypeError, ValueError) as e:
        error_msg = f"Invalid id_documento format: {id_documento}. Error: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    base_url = get_api_base_url()
    api_url = f"{base_url}/documento_by_function/{id_documento}"

    headers = build_django_request_headers(token_auth)
    if "Authorization" not in headers:
        logger.error("No authorization header for update_document_content")

    # Prepare payload
    payload = {"contenido": content}

    logger.info(f"Making API call to update document {id_documento}")
    logger.info(f"API URL: {api_url}")
    logger.info(f"Payload: {payload}")
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

        logger.info(f"Document {id_documento} updated successfully")

        # After successful update, notify transcription completion
        notify_result = notify_transcription_complete(id_documento, token_auth)
        if not notify_result["success"]:
            logger.warning(
                f"Failed to send completion notification: {notify_result.get('error')}"
            )

        return {
            "success": True,
            "status_code": response.status_code,
            "response": response_data,
            "duration_seconds": duration,
        }

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error while updating document {id_documento}: {str(e)}"
        logger.error(
            f"{error_msg}. Check if Django server is running and accessible at {api_url}"
        )
        return {"success": False, "error": error_msg}

    except requests.exceptions.RequestException as e:
        error_msg = f"Error updating document {id_documento}: {str(e)}"
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
                "Authentication failed (401 Unauthorized) - invalid or expired token"
            )
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
        error_msg = f"Unexpected error updating document {id_documento}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}


def send_generation_chunk(
    id_documento: int,
    id_proceso: str,
    chunk: Optional[str] = None,
    is_complete: bool = False,
    is_error: bool = False,
    error: Optional[str] = None,
    token_auth: Optional[str] = None,
    max_retries: int = 1,  # Allow one retry (total of 2 attempts)
) -> Dict[str, Any]:
    """
    Send a chunk of generated content to the Django API.

    Args:
        id_documento: The ID of the document being processed
        id_proceso: The ID of the processing job
        chunk: The content chunk to send
        is_complete: Whether this is the final chunk
        is_error: Whether an error occurred
        error: Error message (if is_error is True)
        token_auth: Authentication token for the Django API
        max_retries: Maximum number of retries on 401 error

    Returns:
        Dictionary containing the API response or error information
    """
    base_url = get_api_base_url()
    api_url = f"{base_url}/document/generation-chunk"

    # Get auth token from parameter or environment
    if not token_auth:
        return {"success": False, "error": "No authentication token available"}

    headers = build_django_request_headers(token_auth)

    # Modified payload creation - ensure all fields are present and have correct types
    payload = {
        "id_documento": int(id_documento),  # Ensure integer
        "id_proceso": str(id_proceso),  # Ensure string
        "is_complete": bool(is_complete),  # Ensure boolean
        "is_error": bool(is_error),  # Ensure boolean
    }

    # Add chunk field (could be None in schema but Django Ninja might require it)
    payload["chunk"] = chunk if chunk is not None else ""

    # Add error field only if applicable
    if is_error and error:
        payload["error"] = str(error)
    else:
        payload["error"] = None  # Explicitly include with None value

    # Debug logging to see what's being sent
    logger.info(f"Sending payload to Django: {payload}")

    # Track retry attempts
    attempts = 0
    max_attempts = max_retries + 1  # Initial attempt + retries

    while attempts < max_attempts:
        attempts += 1
        try:
            logger.info(f"API request attempt {attempts}/{max_attempts}")

            # Make the API request
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)

            # Log detailed information about the response
            logger.info(f"API response status code: {response.status_code}")

            # Enhanced error logging
            if response.status_code >= 400:
                logger.error(f"API error response: {response.status_code}")
                logger.error(f"API response headers: {dict(response.headers)}")

                try:
                    logger.error(f"API response body: {response.text[:500]}")
                except:
                    logger.error("Could not log response body")

                # Special handling for 422 validation errors
                if response.status_code == 422:
                    logger.error(f"Validation error (422): {response.text}")
                    # Try to parse the error message for more details
                    try:
                        error_details = response.json()
                        logger.error(f"Validation error details: {error_details}")
                    except:
                        logger.error(f"Raw validation error: {response.text}")

            # Handle 401 errors specifically
            if response.status_code == 401:
                logger.error(f"Authentication failed (401 Unauthorized)")

                if attempts < max_attempts:
                    logger.info(
                        f"Retrying after 401 error ({attempts}/{max_attempts})..."
                    )
                    continue  # Retry
                else:
                    logger.error("Max retry attempts reached. Giving up.")
                    return {
                        "success": False,
                        "error": "Authentication failed after max retries",
                        "status_code": 401,
                    }

            # For any other status, proceed as normal
            response.raise_for_status()

            logger.info(f"Successfully sent chunk for document {id_documento}")
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response.json() if response.text else {},
            }

        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.error(f"Request error: {str(e)} (status code: {status_code})")

            # Only retry on 401 errors
            if status_code == 401 and attempts < max_attempts:
                logger.info(
                    f"Will retry after 401 error ({attempts}/{max_attempts})..."
                )
                continue

            # Extract more helpful error details when available
            response_text = None
            if hasattr(e, "response") and hasattr(e.response, "text"):
                try:
                    response_text = e.response.text
                    logger.error(f"Error response body: {response_text}")
                except:
                    pass

            return {
                "success": False,
                "error": str(e),
                "status_code": status_code,
                "response_text": response_text,
            }

        except Exception as e:
            logger.error(f"Unexpected error sending chunk: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    # Should never reach here but just in case
    return {"success": False, "error": "Failed after max retries"}
