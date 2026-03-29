"""
Authentication helpers for Django Ninja.

- SessionAuth: optional pattern for Bearer-shaped session checks (rarely used).
- User API JWT (login + /auth/jwt-token) is implemented in apps/users/api.py
  with revocation via jti in cache.

Cloud Function callbacks use utils.auth.JWTAuth (decoded claims dict, no jti).
See documentation/jwt_and_auth_contracts.md.
"""

from ninja.security import HttpBearer
from django.http import HttpRequest
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


class SessionAuth(HttpBearer):
    """
    Session-based authentication for Django Ninja.

    Example:
        @router.get("/protected", auth=SessionAuth())
        def protected_route(request):
            return {"data": "This is protected"}
    """

    def __init__(self, auto_error: bool = True):
        self.auto_error = auto_error

    def authenticate(self, request: HttpRequest, token: str = None) -> Optional[Any]:
        if request.user and request.user.is_authenticated:
            return request.user
        return None
