from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", alias="ENVIRONMENT")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    backend_internal_base_url: str = Field(
        default="http://localhost:8001",
        alias="BACKEND_INTERNAL_BASE_URL",
    )
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="us-east1", alias="GCP_REGION")
    vertex_ai_location: str = Field(default="global", alias="VERTEX_AI_LOCATION")
    cloud_tasks_invoker_service_account: str | None = Field(
        default=None,
        alias="CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT",
    )

    @property
    def environment_name(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_local(self) -> bool:
        return self.environment_name in {"local", "dev", "develop", "test"}

    @property
    def is_production(self) -> bool:
        return self.environment_name in {"prod", "production"}
