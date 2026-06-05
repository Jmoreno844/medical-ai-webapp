from __future__ import annotations

import contextlib
import contextvars
import json
import logging
from datetime import UTC, datetime
from typing import Any


_LOG_CONTEXT: dict[str, contextvars.ContextVar[Any | None]] = {
    "event": contextvars.ContextVar("event", default=None),
    "process_id": contextvars.ContextVar("process_id", default=None),
    "document_id": contextvars.ContextVar("document_id", default=None),
    "section_id": contextvars.ContextVar("section_id", default=None),
    "provider": contextvars.ContextVar("provider", default=None),
    "model": contextvars.ContextVar("model", default=None),
    "error_code": contextvars.ContextVar("error_code", default=None),
    "duration_ms": contextvars.ContextVar("duration_ms", default=None),
    "status_code": contextvars.ContextVar("status_code", default=None),
}

_ALLOWED_LOG_FIELDS = (
    "event",
    "process_id",
    "document_id",
    "section_id",
    "provider",
    "model",
    "error_code",
    "duration_ms",
    "status_code",
)

_SENSITIVE_FIELD_MARKERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "jwt",
    "password",
    "secret",
    "prompt",
    "transcript",
    "transcription",
    "content",
    "chunk",
    "signed_url",
    "callback_token",
}


def bind_log_context(**values: Any) -> contextlib.AbstractContextManager[None]:
    tokens: list[tuple[contextvars.ContextVar[Any | None], contextvars.Token[Any | None]]] = []

    @contextlib.contextmanager
    def _manager():
        try:
            for key, value in values.items():
                variable = _LOG_CONTEXT.get(key)
                if variable is None:
                    continue
                tokens.append((variable, variable.set(value)))
            yield
        finally:
            for variable, token in reversed(tokens):
                variable.reset(token)

    return _manager()


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event: str,
    **fields: Any,
) -> None:
    logger.log(level, message, extra={"event": event, **fields})


class SensitiveTelemetryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__.keys()):
            if key.lower() in _SENSITIVE_FIELD_MARKERS:
                record.__dict__[key] = "[REDACTED]"
        return True


class TraceContextFilter(logging.Filter):
    def __init__(self, *, service_name: str, environment: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name
        record.environment = self._environment
        record.trace_id = None
        record.span_id = None

        try:
            from opentelemetry import trace
            from opentelemetry.trace import format_span_id, format_trace_id

            span = trace.get_current_span()
            context = span.get_span_context()
            if context.is_valid:
                record.trace_id = format_trace_id(context.trace_id)
                record.span_id = format_span_id(context.span_id)
        except Exception:
            record.trace_id = None
            record.span_id = None

        for field in _ALLOWED_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is None:
                value = _LOG_CONTEXT[field].get()
            setattr(record, field, value)
        if record.exc_info and getattr(record, "error_code", None) is None:
            record.error_code = record.exc_info[0].__name__
        return True


class JsonTelemetryFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": getattr(record, "service", None),
            "environment": getattr(record, "environment", None),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        for field in _ALLOWED_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=True, default=str)
