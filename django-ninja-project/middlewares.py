from datetime import datetime


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to HTTP responses.

    These headers help to protect against common web vulnerabilities.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Security Headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
        )
        response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class SessionActivityMiddleware:
    """
    Middleware to track user session activity and enforce inactivity timeouts.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_time = datetime.now().timestamp()

            # Get last activity time
            last_activity = request.session.get("last_activity")
            if last_activity and (current_time - last_activity > 3600):  # 1 hour
                # Session expired due to inactivity
                from django.contrib.auth import logout

                logout(request)
            else:
                # Update last activity time
                request.session["last_activity"] = current_time

        return self.get_response(request)
