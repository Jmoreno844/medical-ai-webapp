from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request, Response, status

from app.core.config import Settings, get_settings


def verify_django_password(password: str, encoded: str) -> bool:
    """Verify Django's default pbkdf2_sha256 password hash."""
    try:
        algorithm, iterations, salt, stored_hash = encoded.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations_int = int(iterations)
    except ValueError:
        return False

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations_int,
    )
    calculated = base64.b64encode(derived).decode("ascii").strip()
    return hmac.compare_digest(calculated, stored_hash)


def make_django_password(password: str, *, iterations: int = 720000) -> str:
    """Create a Django-compatible pbkdf2_sha256 password hash."""
    salt = secrets.token_urlsafe(12)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    encoded_hash = base64.b64encode(derived).decode("ascii").strip()
    return f"pbkdf2_sha256${iterations}${salt}${encoded_hash}"


def create_token(
    *,
    subject: str,
    purpose: str,
    audience: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    token_id = str(uuid4())
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": subject,
        "aud": audience,
        "purpose": purpose,
        "iat": now,
        "exp": now + expires_delta,
        "jti": token_id,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.token_signing_key, algorithm="HS256"), token_id


def password_session_fingerprint(
    encoded_password: str,
    *,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    digest = hmac.new(
        settings.token_signing_key.encode("utf-8"),
        encoded_password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def decode_token(
    token: str,
    *,
    audience: str,
    purpose: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.token_signing_key,
            algorithms=["HS256"],
            audience=audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc

    if payload.get("purpose") != purpose:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token purpose")
    return payload


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    cookie_kwargs = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        httponly=True,
        max_age=settings.access_token_minutes * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        httponly=True,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        **cookie_kwargs,
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for cookie_name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        response.delete_cookie(cookie_name, path="/")


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(request: Request, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if not cookie_token or not header_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token required")
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
