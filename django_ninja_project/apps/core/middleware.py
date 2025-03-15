import sys
import traceback
import json
import logging  # already imported

logger = logging.getLogger(__name__)


class DebugCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        print("!!!!!!!!!! Debug CORS Middleware initialized !!!!!!!!!!", flush=True)
        sys.stdout.flush()

    def __call__(self, request):
        origin = request.headers.get("Origin", "No Origin")
        logger.debug(
            f"DebugCorsMiddleware: Incoming request from {origin}, method: {request.method}"
        )
        # Call subsequent middleware/handler
        response = self.get_response(request)
        logger.debug(
            f"DebugCorsMiddleware: Response status code: {response.status_code}"
        )
        if "Access-Control-Allow-Origin" not in response:
            logger.warning(
                f"DebugCorsMiddleware: Response for request from {origin} is missing 'Access-Control-Allow-Origin' header"
            )
        return response

    # Removed handle_preflight method for non-interception of OPTIONS requests
