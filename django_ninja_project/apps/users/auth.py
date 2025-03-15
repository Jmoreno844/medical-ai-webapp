from ninja.security import HttpBearer
from django.http import HttpRequest
from typing import Optional, Any


class SessionAuth(HttpBearer):
    """
    Session-based authentication for Django Ninja

    This class provides authentication based on Django's session framework.
    It can be used as a dependency for protected routes.

    Example:
        @router.get("/protected", auth=SessionAuth())
        def protected_route(request):
            return {"data": "This is protected"}
    """

    def __init__(self, auto_error: bool = True):
        """
        Initialize the SessionAuth class

        Args:
            auto_error: If True, throw 401 when authentication fails
                        If False, return None (allows optional auth)
        """
        self.auto_error = auto_error

    def authenticate(self, request: HttpRequest, token: str = None) -> Optional[Any]:
        """
        Authenticate the request based on session

        Args:
            request: The HTTP request object
            token: Not used in session auth, kept for compatibility

        Returns:
            The authenticated user or None
        """
        if request.user and request.user.is_authenticated:
            return request.user
        return None
