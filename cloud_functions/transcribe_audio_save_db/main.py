"""
Main entry point for the Google Cloud Function.
Handles HTTP requests and Cloud Events.
"""

import json
import datetime
import functions_framework
import logging

# Import from our modules
from config import get_environment
from utils.logging_utils import setup_logging
from services.summarization import summarize_text
from services.django_api import update_document_content

# Set up logging
logger = setup_logging()


@functions_framework.http
def gemini_handler(request):
    """
    HTTP Cloud Function entry point that summarizes the provided text
    and optionally updates a Django document.

    Args:
        request: The HTTP request object containing text to summarize
                and optional document_id to update

    Returns:
        The HTTP response object with the summarized content and API update status
    """
    # Set CORS headers for the preflight request
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",  # Added Authorization
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    # Set CORS headers for the main request
    headers = {"Access-Control-Allow-Origin": "*"}

    # Handle health check requests
    if request.method == "GET":
        env = get_environment()
        return (
            json.dumps(
                {
                    "status": "ok",
                    "environment": env,
                    "timestamp": str(datetime.datetime.now()),
                    "version": "1.0",
                    "description": "Medical text summarization API",
                }
            ),
            200,
            headers,
        )

    try:
        request_json = request.get_json(silent=True)

        if not request_json:
            return (json.dumps({"error": "No JSON data provided"}), 400, headers)

        # Debug log the entire request payload for troubleshooting
        logger.info(f"Received request payload: {json.dumps(request_json)[:200]}...")

        # Handle test request
        if request_json.get("test") == True:
            return (
                json.dumps(
                    {
                        "success": True,
                        "message": "Test request successful",
                        "environment": get_environment(),
                    }
                ),
                200,
                headers,
            )

        # Check for text field in the request - accept either "text" or "prompt"
        if "text" in request_json:
            text = request_json.get("text")
        elif "prompt" in request_json:
            text = request_json.get("prompt")
        else:
            return (
                json.dumps({"error": "No text or prompt provided for summarization"}),
                400,
                headers,
            )

        model = request_json.get("model")  # Optional model override

        # Get document_id, handling both string and integer formats
        document_id = request_json.get("document_id")

        # Extract auth token with explicit debugging to catch payload issues
        auth_token = None

        # Debug actual request body keys to check if auth_token is present
        logger.info(f"Request JSON keys: {list(request_json.keys())}")

        # First check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            logger.info(f"Found Authorization header: {auth_header[:10]}...")
            if auth_header.startswith("Bearer "):
                auth_token = auth_header.split("Bearer ", 1)[1].strip()
                logger.info(
                    f"Extracted token from Authorization header: {auth_token[:10]}..."
                )
            else:
                auth_token = auth_header
                logger.info(
                    "Authorization header doesn't start with 'Bearer ', using as-is"
                )

        # Specifically check for auth_token in request body with more debugging
        elif "auth_token" in request_json:
            auth_token = request_json.get("auth_token")
            logger.info(
                f"Found auth_token in request body: {auth_token[:10] if auth_token else 'None'}..."
            )

        # If still no token, check other common fields
        if not auth_token:
            for token_field in ["token", "jwt", "jwtToken", "access_token"]:
                if token_field in request_json:
                    auth_token = request_json.get(token_field)
                    logger.info(
                        f"Found token in request body field '{token_field}': {auth_token[:10] if auth_token else 'None'}..."
                    )
                    break

        # Final check - did we find a token?
        if auth_token:
            logger.info(
                f"✅ Successfully extracted auth token (length: {len(auth_token)})"
            )
        else:
            logger.warning("⚠️ No auth token found in request (neither header nor body)")

        # Add specific logging for document_id
        if document_id is not None:
            logger.info(
                f"Document ID received: {document_id} (type: {type(document_id).__name__})"
            )
        else:
            logger.info("No document_id provided, will not update Django API")

        # Summarize the text
        logger.info(f"Starting text summarization, length: {len(text)} characters")
        result = summarize_text(text, model)

        # Check if summarization was successful
        if result.get("success", False):
            # Log processing time
            if "process_time_seconds" in result:
                logger.info(
                    f"Text summarization completed in {result['process_time_seconds']} seconds"
                )

            # If document_id was provided, update the Django document
            if document_id is not None:
                logger.info(f"About to update document {document_id} with summary")
                summary_text = result.get("summary", "")
                logger.info(f"Summary length: {len(summary_text)} characters")

                # Log token presence before making API call
                if auth_token:
                    logger.info("Sending request to Django with auth token...")
                else:
                    logger.warning("No auth token available for Django API request")

                update_result = update_document_content(
                    document_id, summary_text, auth_token
                )

                # Add the update result to the response
                result["document_update"] = update_result

                # Log the update result
                if update_result.get("success", False):
                    logger.info(
                        f"✅ Document {document_id} updated successfully in Django API"
                    )
                else:
                    error_msg = update_result.get("error", "Unknown error")
                    logger.error(
                        f"❌ Failed to update document {document_id}: {error_msg}"
                    )
            else:
                logger.info("Skipping document update as no document_id was provided")

        # Return the response
        status_code = 200 if result.get("success", False) else 500
        return (json.dumps(result), status_code, headers)

    except Exception as e:
        logger.error(f"Error handling request: {str(e)}", exc_info=True)
        return (
            json.dumps(
                {
                    "error": str(e),
                    "message": "An error occurred while processing your request",
                }
            ),
            500,
            headers,
        )


@functions_framework.cloud_event
def gemini_event_handler(cloud_event):
    """

    Args:
        cloud_event: The Cloud Event object

    Returns:
        None
    """
    try:
        # Parse the cloud event data (e.g., from Pub/Sub)
        if cloud_event.data:
            data = json.loads(cloud_event.data["message"]["data"])

            # Check for text or prompt in the event data
            if "text" in data:
                text = data.get("text")
            elif "prompt" in data:
                text = data.get("prompt")
            else:
                logger.error("No text or prompt in event data")
                return {"error": "No text or prompt provided"}

            model_name = data.get("model")

            # Summarize the text
            result = summarize_text(text, model_name)

            # Here you could store the result or publish to another topic
            logger.info(f"Generated summary from event: {result}")
            return result
        else:
            logger.error("No data in cloud event")
            return {"error": "No data in cloud event"}
    except Exception as e:
        logger.error(f"Error handling cloud event: {str(e)}")
        return {"error": str(e)}
