from datetime import timedelta
from http.cookies import SimpleCookie

import pytest
import jwt
from fastapi import HTTPException, Response

from app.core.config import Settings
from app.core.security import (
    create_token,
    decode_token,
    make_django_password,
    password_session_fingerprint,
    verify_django_password,
)
from app.domains.auth.service import issue_browser_tokens
from app.core.service_jwt import (
    issue_generation_callback_token,
    issue_transcription_callback_token,
)
from app.domains.copilot.internal_jwt import (
    decode_copilot_internal_jwt,
    encode_copilot_internal_jwt,
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


def test_make_django_password_is_verifiable_by_django_hash_checker() -> None:
    encoded = make_django_password("testpass123")

    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_django_password("testpass123", encoded)
    assert not verify_django_password("wrong-password", encoded)


def test_transcription_callback_token_uses_callback_audience_and_claims() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_transcription_callback_token(
        user_id=7,
        document_id=42,
        settings=settings,
    )

    payload = decode_token(
        token,
        audience=settings.callback_jwt_audience,
        purpose="transcription",
        settings=settings,
    )

    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.callback_jwt_audience
    assert payload["user_id"] == 7
    assert payload["document_id"] == 42


def test_generation_callback_token_rejects_wrong_purpose_and_audience() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    token = issue_generation_callback_token(
        user_id=7,
        document_id=42,
        process_id="gen_42_123",
        settings=settings,
    )

    payload = decode_token(
        token,
        audience=settings.callback_jwt_audience,
        purpose="document_generation",
        settings=settings,
    )
    assert payload["process_id"] == "gen_42_123"

    with pytest.raises(HTTPException):
        decode_token(
            token,
            audience=settings.sse_jwt_audience,
            purpose="document_generation",
            settings=settings,
        )
    with pytest.raises(HTTPException):
        decode_token(
            token,
            audience=settings.callback_jwt_audience,
            purpose="transcription",
            settings=settings,
        )


def test_issue_browser_tokens_persists_browser_session_id_in_access_and_refresh() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    response = Response()
    user = type(
        "UserStub",
        (),
        {"id": 7, "role": "doctor", "password": make_django_password("testpass123")},
    )()

    session_id = issue_browser_tokens(
        response,
        user,
        settings,
        session_id="session-123",
    )

    cookie = SimpleCookie()
    for key, value in response.raw_headers:
        if key.decode("latin-1").lower() == "set-cookie":
            cookie.load(value.decode("latin-1"))

    access_payload = decode_token(
        cookie[settings.access_cookie_name].value,
        audience=settings.browser_jwt_audience,
        purpose="browser_access",
        settings=settings,
    )
    refresh_payload = decode_token(
        cookie[settings.refresh_cookie_name].value,
        audience=settings.browser_jwt_audience,
        purpose="browser_refresh",
        settings=settings,
    )

    assert session_id == "session-123"
    assert access_payload["sid"] == "session-123"
    assert refresh_payload["sid"] == "session-123"


def test_copilot_broker_jwt_uses_shared_secret_and_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.domains.copilot.internal_jwt.settings.copilot_service_shared_jwt",
        "copilot-shared-secret-at-least-32-bytes",
    )
    monkeypatch.setattr(
        "app.domains.copilot.internal_jwt.settings.copilot_agent_audience",
        "app-api-service",
    )
    token = encode_copilot_internal_jwt(
        purpose="copilot_internal_broker",
        audience="app-api-service",
    )

    payload = decode_copilot_internal_jwt(token=token, audience="app-api-service")

    assert payload["iss"] == "app-api-service"
    assert payload["sub"] == "fastapi-copilot-broker"
    assert payload["purpose"] == "copilot_internal_broker"


def test_copilot_tools_jwt_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.domains.copilot.internal_jwt.settings.copilot_service_shared_jwt",
        "copilot-shared-secret-at-least-32-bytes",
    )
    token = encode_copilot_internal_jwt(
        purpose="copilot_internal_tools",
        audience="wrong-audience",
        issuer="copilot-agent-service",
        subject="copilot-agent-tools",
        extra_claims={
            "run_id": "run_1",
            "thread_id": "thread_1",
            "encounter_id": "3",
            "user_id": "7",
        },
    )

    with pytest.raises(jwt.InvalidAudienceError):
        decode_copilot_internal_jwt(token=token, audience="medical-api")
