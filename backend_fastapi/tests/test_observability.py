from __future__ import annotations

import io
import json
import logging

import pytest

from app.core.observability import bind_log_context
from app.core.logging import configure_logging
from app.core.settings.base import Settings
from app.core.tracing import _resolve_exporter_mode


def _build_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    settings = Settings(ENVIRONMENT="test", DEBUG=False)
    configure_logging(settings, service_name="test-backend")
    root = logging.getLogger()
    assert root.handlers
    root.handlers[0].stream = stream
    return logging.getLogger("tests.observability"), stream


def test_json_logging_uses_allowlisted_fields_only() -> None:
    logger, stream = _build_logger()

    with bind_log_context(process_id="gen_1", document_id=7):
        logger.info(
            "Document event",
            extra={
                "event": "document_generated",
                "authorization": "secret-token",
                "model": "claude-haiku-4-5-20251001",
            },
        )

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "test-backend"
    assert payload["environment"] == "test"
    assert payload["event"] == "document_generated"
    assert payload["process_id"] == "gen_1"
    assert payload["document_id"] == 7
    assert payload["model"] == "claude-haiku-4-5-20251001"
    assert "authorization" not in payload


def test_json_logging_uses_exception_type_as_error_code() -> None:
    logger, stream = _build_logger()

    try:
        raise ValueError("Paciente Juan Perez")
    except ValueError:
        logger.exception("Worker failed", extra={"event": "worker_failed"})

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "worker_failed"
    assert payload["error_code"] == "ValueError"
    assert "Paciente Juan Perez" not in stream.getvalue()


def test_resolve_exporter_mode_respects_explicit_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "1")
    assert _resolve_exporter_mode() == "none"
