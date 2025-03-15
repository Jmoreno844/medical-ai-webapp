import logging
from urllib.parse import urlparse
from django.conf import settings

logger = logging.getLogger(__name__)


class CorsSkipMiddleware:
    """
    Middleware to conditionally bypass CORS restrictions for specific origins.

    This middleware should only be used in development and testing environments.
    It allows authorized testing origins to bypass CORS restrictions by setting
    special attributes on the request object that can be checked by other middleware.
    """

    def __init__(self, get_response):
        """Initialize the middleware with response handler and trusted origins."""
        self.get_response = get_response

        # Warn if this middleware is active in production
        if not getattr(settings, "DEBUG", False):
            logger.warning(
                "CorsSkipMiddleware is enabled in a non-DEBUG environment. "
                "This middleware should only be used in development/testing."
            )

        # Get list of trusted origins that can bypass CORS checks
        self.trusted_origins = getattr(settings, "CORS_SKIP_TRUSTED_ORIGINS", [])

        if self.trusted_origins:
            logger.info(
                f"CorsSkipMiddleware initialized with trusted origins: {self.trusted_origins}"
            )
        else:
            logger.debug("CorsSkipMiddleware initialized without any trusted origins")

    def __call__(self, request):
        """Process each request to determine if CORS checks should be skipped."""
        # Extract the Origin header
        origin = request.headers.get("Origin")

        if origin:
            try:
                # Parse the origin to extract domain/hostname
                parsed_origin = urlparse(origin)
                request_host = parsed_origin.netloc or parsed_origin.path

                # Check if this origin should bypass CORS restrictions
                if any(trusted in request_host for trusted in self.trusted_origins):
                    logger.debug(f"Bypassing CORS for trusted origin: {origin}")
                    # Set attribute on request to signal other middleware
                    request.cors_bypass = True
                else:
                    logger.debug(f"Origin not trusted for CORS bypass: {origin}")
                    request.cors_bypass = False
            except Exception as e:
                logger.error(f"Error processing origin {origin}: {str(e)}")
                request.cors_bypass = False
        else:
            # No Origin header in the request
            logger.debug("No Origin header in request, not applying CORS bypass")
            request.cors_bypass = False

        # Process the request and return the response
        response = self.get_response(request)
        return response
