import logging

logger = logging.getLogger(__name__)


class DebugCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        logger.info("DebugCorsMiddleware initialized")

    def __call__(self, request):
        # Log request details before CORS processing
        origin = request.headers.get("Origin", "No Origin")
        logger.info(
            f"CORS Debug - Incoming request: {request.method} {request.path} from {origin}"
        )

        response = self.get_response(request)

        # Log response CORS headers
        cors_headers = {
            k: v for k, v in response.headers.items() if "cors" in k.lower()
        }
        logger.info(f"CORS Debug - Response headers: {cors_headers}")

        return response
