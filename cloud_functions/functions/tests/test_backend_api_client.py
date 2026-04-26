import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import backend_api


def test_backend_api_base_url_targets_fastapi_v1(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com")
    assert backend_api.get_api_base_url() == "https://backend.example.com/api/v1"


def test_backend_api_base_url_normalizes_legacy_api_suffix(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com/api")
    assert backend_api.get_api_base_url() == "https://backend.example.com/api/v1"


def test_backend_api_base_url_uses_configured_api_version(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com/api/v1")
    monkeypatch.setenv("BACKEND_API_VERSION", "v2")
    assert backend_api.get_api_base_url() == "https://backend.example.com/api/v2"


def test_backend_api_base_url_strips_any_existing_version(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com/api/v17")
    monkeypatch.setenv("BACKEND_API_VERSION", "v3")
    assert backend_api.get_api_base_url() == "https://backend.example.com/api/v3"


def test_backend_api_base_url_default_local_port(monkeypatch):
    monkeypatch.delenv("BACKEND_API_BASE_URL", raising=False)
    assert backend_api.get_api_base_url() == "http://localhost:8001/api/v1"


@patch("services.backend_api.requests.patch")
@patch("services.backend_api.notify_transcription_complete")
def test_update_document_content_calls_fastapi_v1(
    mock_notify,
    mock_patch,
    monkeypatch,
):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com")
    mock_notify.return_value = {"success": True}
    mock_patch.return_value.status_code = 200
    mock_patch.return_value.text = "{}"
    mock_patch.return_value.json.return_value = {}

    result = backend_api.update_document_content(123, "hola", "token")

    assert result["success"] is True
    mock_patch.assert_called_once()
    assert (
        mock_patch.call_args.args[0]
        == "https://backend.example.com/api/v1/documents/by-function/123"
    )


@patch("services.backend_api.requests.post")
def test_send_generation_chunk_calls_fastapi_v1(mock_post, monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://backend.example.com")
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = "{}"
    mock_post.return_value.json.return_value = {}

    result = backend_api.send_generation_chunk(
        document_id=123,
        process_id="gen_123",
        chunk="hola",
        token_auth="token",
    )

    assert result["success"] is True
    mock_post.assert_called_once()
    assert (
        mock_post.call_args.args[0]
        == "https://backend.example.com/api/v1/documents/generation-chunk"
    )
