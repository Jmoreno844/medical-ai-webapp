"""
Service for interacting with the transactional backend API.

The module name is legacy. During the FastAPI migration these callbacks target
the versioned FastAPI `/api/{version}` contract. DJANGO_API_BASE_URL remains a
temporary fallback while platform environment variables are migrated.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


DEFAULT_BACKEND_API_BASE_URL = "http://localhost:8000"
DEFAULT_BACKEND_API_VERSION = "v1"


def build_backend_request_headers(
    token_auth: Optional[str] = None, json_body: bool = True
) -> Dict[str, str]:
    """
    Build HTTP headers for backend API calls.
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


def build_django_request_headers(
    token_auth: Optional[str] = None, json_body: bool = True
) -> Dict[str, str]:
    """Legacy alias kept for callers that still import the Django-named helper."""
    return build_backend_request_headers(token_auth, json_body)


def _backend_api_version() -> str:
    version = os.environ.get("BACKEND_API_VERSION", DEFAULT_BACKEND_API_VERSION).strip()
    if not version:
        version = DEFAULT_BACKEND_API_VERSION
    return version if version.startswith("v") else f"v{version}"


def _normalize_backend_base_url(api_base_url: str) -> str:
    api_base_url = api_base_url.rstrip("/")
    versioned_api_match = re.search(r"/api/v[^/]+$", api_base_url)
    if versioned_api_match:
        return api_base_url[: versioned_api_match.start()]
    if api_base_url.endswith("/api"):
        return api_base_url[: -len("/api")]
    return api_base_url


def get_backend_api_base_url() -> str:
    """Get the versioned backend API base URL used by Cloud Function callbacks."""
    api_base_url = os.environ.get("BACKEND_API_BASE_URL") or os.environ.get(
        "DJANGO_API_BASE_URL"
    )
    if not api_base_url:
        logger.warning(
            "BACKEND_API_BASE_URL/DJANGO_API_BASE_URL not set, using default: %s",
            DEFAULT_BACKEND_API_BASE_URL,
        )
        api_base_url = DEFAULT_BACKEND_API_BASE_URL

    root_url = _normalize_backend_base_url(api_base_url)
    return f"{root_url}/api/{_backend_api_version()}"


def get_api_base_url():
    """Legacy alias for the FastAPI v1 backend base URL."""
    return get_backend_api_base_url()


def notify_transcription_complete(
    document_id: int, token_auth: Optional[str] = None
) -> Dict[str, Any]:
    base_url = get_api_base_url()
    api_url = f"{base_url}/transcription/notify-complete"

    headers = build_backend_request_headers(token_auth)

    payload = {
        "document_id": document_id,
        "status": "complete",
    }

    logger.info(f"Notifying transcription completion for document {document_id}")

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        logger.info(
            f"Successfully notified about document {document_id} transcription completion"
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
    document_id: int, content: str, token_auth: Optional[str] = None
) -> Dict[str, Any]:
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
    api_url = f"{base_url}/documents/by-function/{document_id}"

    headers = build_backend_request_headers(token_auth)
    if "Authorization" not in headers:
        logger.error("No authorization header for update_document_content")

    payload = {"content": content}

    logger.info(f"Making API call to update document {document_id}")
    logger.info(f"API URL: {api_url}")
    logger.info(f"Payload keys: {list(payload.keys())}")
    try:
        start_time = time.time()

        response = requests.patch(api_url, json=payload, headers=headers, timeout=30)

        end_time = time.time()
        duration = round(end_time - start_time, 2)

        logger.info(
            f"API response received in {duration} seconds with status code: {response.status_code}"
        )

        response.raise_for_status()

        try:
            response_data = response.json()
        except json.JSONDecodeError:
            response_data = {"raw_response": response.text}

        logger.info(f"Document {document_id} updated successfully")

        notify_result = notify_transcription_complete(document_id, token_auth)
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
        error_msg = f"Connection error while updating document {document_id}: {str(e)}"
        logger.error(f"{error_msg}. Check if backend is accessible at {api_url}")
        return {"success": False, "error": error_msg}

    except requests.exceptions.RequestException as e:
        error_msg = f"Error updating document {document_id}: {str(e)}"
        logger.error(error_msg)

        status_code = None
        response_text = None
        if hasattr(e, "response"):
            status_code = getattr(e.response, "status_code", None)
            try:
                response_text = e.response.text
            except Exception:
                pass

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
        error_msg = f"Unexpected error updating document {document_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}


def send_generation_chunk(
    document_id: int,
    process_id: str,
    chunk: Optional[str] = None,
    is_complete: bool = False,
    is_error: bool = False,
    error: Optional[str] = None,
    token_auth: Optional[str] = None,
    max_retries: int = 1,
) -> Dict[str, Any]:
    base_url = get_api_base_url()
    api_url = f"{base_url}/documents/generation-chunk"

    if not token_auth:
        return {"success": False, "error": "No authentication token available"}

    headers = build_backend_request_headers(token_auth)

    payload = {
        "document_id": int(document_id),
        "process_id": str(process_id),
        "is_complete": bool(is_complete),
        "is_error": bool(is_error),
    }

    payload["chunk"] = chunk if chunk is not None else ""

    if is_error and error:
        payload["error"] = str(error)
    else:
        payload["error"] = None

    chunk_len = len(payload.get("chunk") or "")
    logger.info(
        "Sending generation chunk to backend: document_id=%s process_id=%s "
        "is_complete=%s is_error=%s chunk_len=%s",
        payload.get("document_id"),
        payload.get("process_id"),
        payload.get("is_complete"),
        payload.get("is_error"),
        chunk_len,
    )

    attempts = 0
    max_attempts = max_retries + 1

    while attempts < max_attempts:
        attempts += 1
        try:
            logger.info(f"API request attempt {attempts}/{max_attempts}")

            response = requests.post(api_url, json=payload, headers=headers, timeout=10)

            logger.info(f"API response status code: {response.status_code}")

            if response.status_code >= 400:
                logger.error(f"API error response: {response.status_code}")
                logger.error(f"API response headers: {dict(response.headers)}")

                try:
                    logger.error(f"API response body: {response.text[:500]}")
                except Exception:
                    logger.error("Could not log response body")

                if response.status_code == 422:
                    logger.error(f"Validation error (422): {response.text}")
                    try:
                        error_details = response.json()
                        logger.error(f"Validation error details: {error_details}")
                    except Exception:
                        logger.error(f"Raw validation error: {response.text}")

            if response.status_code == 401:
                logger.error("Authentication failed (401 Unauthorized)")

                if attempts < max_attempts:
                    logger.info(
                        f"Retrying after 401 error ({attempts}/{max_attempts})..."
                    )
                    continue
                else:
                    logger.error("Max retry attempts reached. Giving up.")
                    return {
                        "success": False,
                        "error": "Authentication failed after max retries",
                        "status_code": 401,
                    }

            response.raise_for_status()

            logger.info(f"Successfully sent chunk for document {document_id}")
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response.json() if response.text else {},
            }

        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.error(f"Request error: {str(e)} (status code: {status_code})")

            if status_code == 401 and attempts < max_attempts:
                logger.info(
                    f"Will retry after 401 error ({attempts}/{max_attempts})..."
                )
                continue

            response_text = None
            if hasattr(e, "response") and hasattr(e.response, "text"):
                try:
                    response_text = e.response.text
                    logger.error(f"Error response body: {response_text}")
                except Exception:
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

    return {"success": False, "error": "Failed after max retries"}
