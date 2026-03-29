from ninja.security import HttpBearer
import jwt
from django.conf import settings
from typing import Optional
import logging

from utils.jwt_settings import get_jwt_signing_key

logger = logging.getLogger(__name__)


class JWTAuth(HttpBearer):
    """
    Bearer JWT for Cloud Function callbacks and internal service tokens.

    Returns the decoded claims dict. Does not use jti blacklist (that applies
    only to user API tokens in apps/users/api.py).
    """

    def authenticate(self, request, token: str) -> Optional[dict]:
        if not token:
            logger.warning("JWTAuth: missing token")
            return None

        try:
            payload = jwt.decode(
                token, get_jwt_signing_key(), algorithms=["HS256"]
            )
            logger.debug(
                "JWTAuth: decoded token purpose=%s keys=%s",
                payload.get("purpose"),
                list(payload.keys()),
            )

            # Optional sanity: generation flow should include id_proceso
            purpose = payload.get("purpose")
            if purpose == "sse_connection":
                if "id_documento" not in payload or "id_usuario" not in payload:
                    logger.warning("JWTAuth: SSE token missing id_documento or id_usuario")
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWTAuth: token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("JWTAuth: invalid token (%s)", type(e).__name__)
            return None
        except Exception as e:
            logger.exception("JWTAuth: unexpected error: %s", e)
            return None
