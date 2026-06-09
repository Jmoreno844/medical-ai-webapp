from __future__ import annotations

from app.core.config import Settings


def is_local_environment(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {
        "local",
        "dev",
        "development",
        "test",
        "ci",
    }
