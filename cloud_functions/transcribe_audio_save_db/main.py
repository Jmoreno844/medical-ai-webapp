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

# Set up logging
logger = setup_logging()


@functions_framework.http
def gemini_handler(request):
    """
    HTTP Cloud Function entry point that summarizes the provided text.

    Args:
        request: The HTTP request object containing text to summarize

    Returns:
        The HTTP response object with the summarized content
    """
    # Set CORS headers for the preflight request
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET",
            "Access-Control-Allow-Headers": "Content-Type",
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

        # Summarize the text
        result = summarize_text(text, model)

        # Return the response
        status_code = 200 if result.get("success", False) else 500
        return (json.dumps(result), status_code, headers)

    except Exception as e:
        logger.error(f"Error handling request: {str(e)}")
        return (json.dumps({"error": str(e)}), 500, headers)


@functions_framework.cloud_event
def gemini_event_handler(cloud_event):
    """
    Cloud Event handler for processing Pub/Sub messages.

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
