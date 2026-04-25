from __future__ import annotations

from pydantic import Field

from app.core.settings.base import BASE_DIR, COMMON_SETTINGS_CONFIG
from app.core.settings.prod import ProductionSettings


class StagingSettings(ProductionSettings):
    model_config = COMMON_SETTINGS_CONFIG | {
        "env_file": (BASE_DIR / ".env.stg",),
    }

    environment: str = Field(default="staging", alias="ENVIRONMENT")
