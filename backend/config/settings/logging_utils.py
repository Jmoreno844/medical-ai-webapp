"""
Shared Django LOGGING dict builder. Level is controlled by env ``DJANGO_LOG_LEVEL``
(``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``). Invalid values fall back to *default_level*.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

_VALID = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class TraceContextFilter(logging.Filter):
    """Attach trace/span IDs from the current OpenTelemetry span to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import format_span_id, format_trace_id

            span = trace.get_current_span()
            sc = span.get_span_context()
            if sc.is_valid:
                record.trace_id = format_trace_id(sc.trace_id)
                record.span_id = format_span_id(sc.span_id)
                project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
                if project:
                    record.google_cloud_trace = (
                        f"projects/{project}/traces/{format_trace_id(sc.trace_id)}"
                    )
                else:
                    record.google_cloud_trace = "-"
            else:
                record.trace_id = "-"
                record.span_id = "-"
                record.google_cloud_trace = "-"
        except Exception:
            record.trace_id = "-"
            record.span_id = "-"
            record.google_cloud_trace = "-"
        return True


def resolve_log_level(default_level: str) -> str:
    raw = os.getenv("DJANGO_LOG_LEVEL", default_level).strip().upper()
    return raw if raw in _VALID else default_level.upper()


def build_console_logging(default_level: str = "INFO") -> Dict[str, Any]:
    level = resolve_log_level(default_level)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "trace_context": {
                "()": "config.settings.logging_utils.TraceContextFilter",
            },
        },
        "formatters": {
            "standard": {
                "format": (
                    "[{levelname}] {asctime} {name} trace_id={trace_id} "
                    "span_id={span_id} {message}"
                ),
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "filters": ["trace_context"],
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }
