import logging


class CORSMiddlewareWrapper:
    """Emergency CORS wrapper for ASGI/WSGI applications."""

    def __init__(self, application):
        self.app = application
        logging.warning("!!! Emergency CORS wrapper initialized !!!")

    def __call__(self, environ, start_response):
        # Check if this is an OPTIONS request
        if environ.get("REQUEST_METHOD") == "OPTIONS":
            logging.warning(f"OPTIONS request received for: {environ.get('PATH_INFO')}")

            # Get the origin if present
            origin = environ.get("HTTP_ORIGIN", "")
            logging.warning(f"Request origin: {origin}")

            # Define CORS headers for OPTIONS response
            headers = [
                ("Access-Control-Allow-Origin", origin or "*"),
                ("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS"),
                (
                    "Access-Control-Allow-Headers",
                    "Content-Type,Authorization,X-CSRFToken",
                ),
                ("Access-Control-Allow-Credentials", "true"),
                ("Access-Control-Max-Age", "86400"),
                ("Content-Type", "text/plain"),
                ("Content-Length", "0"),
            ]

            # Return 200 OK with CORS headers
            logging.warning("Returning OPTIONS response with CORS headers")
            start_response("200 OK", headers)
            return [b""]

        # For non-OPTIONS requests, pass through to the application
        def cors_start_response(status, response_headers, exc_info=None):
            # Get the origin if present
            origin = environ.get("HTTP_ORIGIN", "")

            # Add CORS headers to the response
            cors_headers = [
                ("Access-Control-Allow-Origin", origin or "*"),
                ("Access-Control-Allow-Credentials", "true"),
            ]

            # Combine headers
            all_headers = response_headers + cors_headers
            return start_response(status, all_headers, exc_info)

        # Pass request to the application with modified start_response
        return self.app(environ, cors_start_response)
