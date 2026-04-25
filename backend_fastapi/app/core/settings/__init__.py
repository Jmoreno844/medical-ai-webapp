from __future__ import annotations

from functools import lru_cache
from os import environ

from app.core.settings.base import Settings
from app.core.settings.local import LocalSettings
from app.core.settings.prod import ProductionSettings
from app.core.settings.stg import StagingSettings
from app.core.settings.test import TestSettings


EnvironmentSettings = LocalSettings | TestSettings | StagingSettings | ProductionSettings


def _settings_class_for_environment(environment: str) -> type[EnvironmentSettings]:
    normalized = environment.strip().lower()
    if normalized in {"local", "dev", "development"}:
        return LocalSettings
    if normalized in {"test", "ci"}:
        return TestSettings
    if normalized in {"stg", "staging"}:
        return StagingSettings
    if normalized in {"prod", "production"}:
        return ProductionSettings
    raise RuntimeError(
        "ENVIRONMENT must be one of local, dev, development, test, ci, "
        "stg, staging, prod, production"
    )


@lru_cache
def get_settings() -> EnvironmentSettings:
    environment = environ.get("ENVIRONMENT", "local")
    return _settings_class_for_environment(environment)()


__all__ = [
    "EnvironmentSettings",
    "LocalSettings",
    "ProductionSettings",
    "Settings",
    "StagingSettings",
    "TestSettings",
    "get_settings",
]
