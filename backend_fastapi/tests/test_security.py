from datetime import timedelta

from app.core.config import Settings
from app.core.security import (
    create_token,
    decode_token,
    password_session_fingerprint,
)


def test_token_requires_expected_purpose_and_audience() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token, token_id = create_token(
        subject="123",
        purpose="browser_access",
        audience=settings.browser_jwt_audience,
        expires_delta=timedelta(minutes=5),
        settings=settings,
    )

    payload = decode_token(
        token,
        audience=settings.browser_jwt_audience,
        purpose="browser_access",
        settings=settings,
    )

    assert payload["sub"] == "123"
    assert payload["jti"] == token_id


def test_password_session_fingerprint_changes_with_password_hash() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")

    first = password_session_fingerprint(
        "pbkdf2_sha256$720000$salt$hash-one",
        settings=settings,
    )
    second = password_session_fingerprint(
        "pbkdf2_sha256$720000$salt$hash-two",
        settings=settings,
    )

    assert first != second
    assert len(first) == 32
