from types import SimpleNamespace

from google.auth.exceptions import TransportError

from app.integrations.storage import (
    _GCS_IAM_SIGNING_SCOPES,
    _bind_adc_iam_signing_kwargs,
    _credentials_for_iam_signing,
    _gcs_signed_url_error_detail,
    _uses_adc_iam_signing,
    upload_url_user_error_message,
)


def test_uses_adc_iam_signing_when_sign_bytes_missing() -> None:
    credentials = SimpleNamespace(sign_bytes=None)
    assert _uses_adc_iam_signing(credentials) is True


def test_uses_adc_iam_signing_when_sign_bytes_is_callable() -> None:
    credentials = SimpleNamespace(sign_bytes=lambda _message: b"signed")
    assert _uses_adc_iam_signing(credentials) is False


def test_credentials_for_iam_signing_requests_cloud_platform_scope() -> None:
    scopes_used: list[tuple[str, ...]] = []
    scoped_credentials = object()

    def with_scopes(scopes: tuple[str, ...]) -> object:
        scopes_used.append(scopes)
        return scoped_credentials

    credentials = SimpleNamespace(with_scopes=with_scopes)
    assert _credentials_for_iam_signing(credentials) is scoped_credentials
    assert scopes_used == [_GCS_IAM_SIGNING_SCOPES]


def test_bind_adc_iam_signing_kwargs_uses_scoped_refresh_not_storage_token() -> None:
    refresh_calls: list[object] = []
    scoped_credentials = SimpleNamespace(
        token=None,
        service_account_email="default",
    )

    def refresh(request: object) -> None:
        refresh_calls.append(request)
        scoped_credentials.token = "scoped-token"
        scoped_credentials.service_account_email = (
            "backend-runner@vext-stg.iam.gserviceaccount.com"
        )

    scoped_credentials.refresh = refresh

    credentials = SimpleNamespace(
        token="unscoped-token",
        service_account_email="backend-runner@vext-stg.iam.gserviceaccount.com",
        with_scopes=lambda _scopes: scoped_credentials,
    )
    signed_url_kwargs: dict[str, object] = {}
    request = object()

    _bind_adc_iam_signing_kwargs(credentials, signed_url_kwargs, request=request)

    assert refresh_calls == [request]
    assert signed_url_kwargs == {
        "service_account_email": "backend-runner@vext-stg.iam.gserviceaccount.com",
        "access_token": "scoped-token",
    }


def test_gcs_signed_url_error_detail_includes_iam_response() -> None:
    exc = TransportError(
        'Error calling the IAM signBytes API: {"error":{"code":403}}'
    )
    assert "IAM signBytes API" in _gcs_signed_url_error_detail(exc)


def test_upload_url_user_error_message_is_stable_for_clients() -> None:
    exc = TransportError("backend detail")
    assert upload_url_user_error_message(exc) == (
        "No se pudo preparar la subida de audio: TransportError"
    )
