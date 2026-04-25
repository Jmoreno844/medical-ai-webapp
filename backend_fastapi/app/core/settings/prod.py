from __future__ import annotations

from pydantic import Field

from app.core.settings.base import COMMON_SETTINGS_CONFIG, StrictDeploymentSettings


class ProductionSettings(StrictDeploymentSettings):
    model_config = COMMON_SETTINGS_CONFIG

    environment: str = Field(default="production", alias="ENVIRONMENT")
