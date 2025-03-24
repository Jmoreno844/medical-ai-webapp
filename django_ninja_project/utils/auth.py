from ninja.security import HttpBearer
import jwt
from django.conf import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class JWTAuth(HttpBearer):
    def authenticate(self, request, token: str) -> Optional[dict]:
        """
        Authenticate the request using JWT token.

        Args:
            request: The HTTP request
            token: The JWT token (without 'Bearer' prefix)

        Returns:
            dict: The decoded token payload if valid, None otherwise
        """
        logger.info(f"JWTAuth.authenticate called with token: {token[:10]}...")
        logger.info(f"JWT_SECRET_KEY length: {len(settings.JWT_SECRET_KEY)}")
        logger.info(f"Headers: {dict(request.headers)}")

        if not token:
            logger.error("No token provided")
            return None

        try:
            # Decode and verify the token
            logger.info(
                f"Attempting to decode token with SECRET_KEY: {settings.JWT_SECRET_KEY[:3]}..."
            )
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])

            # Log detailed info about the decoded token
            logger.info(
                f"Token decoded successfully with payload keys: {list(payload.keys())}"
            )

            # Check for expected fields in token payload
            expected_fields = ["id_documento", "id_usuario", "id_proceso"]
            missing_fields = [
                field for field in expected_fields if field not in payload
            ]
            if missing_fields:
                logger.warning(f"Token missing expected fields: {missing_fields}")

            return payload
        except jwt.ExpiredSignatureError:
            logger.error("Authentication failed: Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.error(f"Authentication failed: Invalid token. Error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
