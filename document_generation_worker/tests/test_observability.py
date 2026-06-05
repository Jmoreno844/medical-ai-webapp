from __future__ import annotations

import io
import json
import logging

from app.logging_config import configure_logging
from app.observability import bind_log_context
from app.settings import Settings


def test_worker_logging_is_json_and_metadata_only() -> None:
    stream = io.StringIO()
    settings = Settings(_env_file=None, ENVIRONMENT="test")
    configure_logging(
        settings,
        service_name="test-document-generation-worker",
    )
    root = logging.getLogger()
    assert root.handlers
    root.handlers[0].stream = stream
    logger = logging.getLogger("tests.document_worker")

    with bind_log_context(process_id="gen_7", document_id=11, provider="anthropic_api"):
        logger.info(
            "Chunk callback sent",
            extra={
                "event": "generation_chunk_sent",
                "callback_token": "secret",
                "model": "claude-haiku-4-5-20251001",
            },
        )

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "test-document-generation-worker"
    assert payload["process_id"] == "gen_7"
    assert payload["document_id"] == 11
    assert payload["provider"] == "anthropic_api"
    assert payload["model"] == "claude-haiku-4-5-20251001"
    assert "callback_token" not in payload
