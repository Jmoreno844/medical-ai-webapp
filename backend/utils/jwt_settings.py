"""
Single source for which secret signs/verifies JWTs in this project.

User-facing API tokens (/auth/jwt-token) and Cloud Function callback tokens
both use the same signing key when JWT_SECRET_KEY is configured.
"""

from django.conf import settings


def get_jwt_signing_key() -> str:
    """
    Return the key used for HS256 JWT signing and verification.

    Prefers settings.JWT_SECRET_KEY when it is set and not a dev placeholder.
    Falls back to Django SECRET_KEY for local setups where JWT_SECRET_KEY
    was never configured.
    """
    key = getattr(settings, "JWT_SECRET_KEY", None)
    if key and str(key).strip() and str(key) != "not-loaded":
        return str(key)
    return str(settings.SECRET_KEY)
