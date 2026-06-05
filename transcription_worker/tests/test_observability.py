from __future__ import annotations

import io
import json
import logging

from app.logging_config import configure_logging
from app.observability import bind_log_context
from app.settings import Settings


def test_transcription_worker_logging_is_json_and_metadata_only() -> None:
    stream = io.StringIO()
    settings = Settings(_env_file=None, ENVIRONMENT="test")
    configure_logging(
        settings,
        service_name="test-transcription-worker",
    )
    root = logging.getLogger()
    assert root.handlers
    root.handlers[0].stream = stream
    logger = logging.getLogger("tests.transcription_worker")

    with bind_log_context(section_id="section_3", provider="google_genai"):
        logger.warning(
            "VAD fail open",
            extra={
                "event": "vad_fail_open",
                "error_code": "RuntimeError",
                "transcript": "Paciente refiere tos",
            },
        )

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "test-transcription-worker"
    assert payload["section_id"] == "section_3"
    assert payload["provider"] == "google_genai"
    assert payload["error_code"] == "RuntimeError"
    assert "transcript" not in payload
