"""
Shared Django LOGGING dict builder. Level is controlled by env ``DJANGO_LOG_LEVEL``
(``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``). Invalid values fall back to *default_level*.
"""

from __future__ import annotations

import os
from typing import Any, Dict

_VALID = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def resolve_log_level(default_level: str) -> str:
    raw = os.getenv("DJANGO_LOG_LEVEL", default_level).strip().upper()
    return raw if raw in _VALID else default_level.upper()


def build_console_logging(default_level: str = "INFO") -> Dict[str, Any]:
    level = resolve_log_level(default_level)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[{levelname}] {asctime} {name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
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
