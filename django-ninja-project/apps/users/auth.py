from ninja.security import HttpBearer
from django.http import HttpRequest
from typing import Optional, Any
import jwt
import os
from django.conf import settings
from django.core.cache import cache
from datetime import datetime
from apps.users.models import User
import logging

logger = logging.getLogger(__name__)


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


class JWTAuth(HttpBearer):
    """
    JWT-based authentication for Django Ninja API

    This authenticator validates JWT tokens and ensures they haven't been
    revoked or expired.
    """

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error)
        self.secret_key = os.getenv("JWT_SECRET_KEY", settings.SECRET_KEY)

    def authenticate(self, request: HttpRequest, token: str) -> Optional[Any]:
        if not token:
            return None

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"verify_signature": True},
            )

            # Check expiration (redundant as JWT decode also checks this)
            exp = payload.get("exp")
            if not exp or datetime.utcnow().timestamp() > exp:
                logger.warning("Expired JWT token used")
                return None

            # Check token revocation
            token_id = payload.get("jti")
            if not token_id:
                logger.warning("JWT without jti claim")
                return None

            # Check if token is blacklisted
            if cache.get(f"jwt_blacklist:{token_id}"):
                logger.warning(f"Revoked JWT token used: {token_id}")
                return None

            # Get and return the user
            user_id = payload.get("user_id")
            try:
                return User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.warning(f"JWT used with non-existent user: {user_id}")
                return None

        except jwt.PyJWTError as e:
            logger.warning(f"JWT validation failed: {str(e)}")
            return None
