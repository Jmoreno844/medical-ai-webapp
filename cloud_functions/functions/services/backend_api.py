"""
HTTP client for Cloud Function callbacks to the main backend (FastAPI `/api/v1`).
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_BACKEND_API_BASE_URL = "http://localhost:8001"
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
    """Versioned base URL e.g. https://host/api/v1 (used by callback paths)."""
    api_base_url = (os.environ.get("BACKEND_API_BASE_URL") or "").strip()
    if not api_base_url:
        logger.warning(
            "BACKEND_API_BASE_URL not set, using default: %s",
            DEFAULT_BACKEND_API_BASE_URL,
        )
        api_base_url = DEFAULT_BACKEND_API_BASE_URL

    root_url = _normalize_backend_base_url(api_base_url)
    return f"{root_url}/api/{_backend_api_version()}"


def get_api_base_url() -> str:
    """Alias for :func:`get_backend_api_base_url` (keeps test and call sites short)."""
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
