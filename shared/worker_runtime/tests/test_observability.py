from __future__ import annotations

import io
import json
import logging

from worker_runtime.logging import configure_logging
from worker_runtime.observability import bind_log_context
from worker_runtime.settings import BaseWorkerSettings


def test_logging_redacts_sensitive_fields() -> None:
    stream = io.StringIO()
    settings = BaseWorkerSettings(_env_file=None, ENVIRONMENT="test")
    configure_logging(settings, service_name="test-worker")
    root = logging.getLogger()
    root.handlers[0].stream = stream
    logger = logging.getLogger("tests.worker_runtime")

    with bind_log_context(session_id="sess-1", provider="gemini"):
        logger.info(
            "callback sent",
            extra={"event": "callback_sent", "callback_token": "secret"},
        )

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "test-worker"
    assert payload["session_id"] == "sess-1"
    assert payload["provider"] == "gemini"
    assert "callback_token" not in payload
