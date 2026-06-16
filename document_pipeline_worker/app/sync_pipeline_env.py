"""Bridge worker Settings into os.environ for ported ai-pipeline providers."""

from __future__ import annotations

import os

from app.settings import Settings

_SETTINGS_TO_ENV: tuple[tuple[str, str], ...] = (
    ("GCP_PROJECT_ID", "gcp_project_id"),
    ("VERTEX_AI_LOCATION", "vertex_ai_location"),
    ("GCP_REGION", "gcp_region"),
    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    ("OPENAI_API_KEY", "openai_api_key"),
    ("OPENAI_MODEL", "openai_model"),
)


def sync_pipeline_runtime_env(settings: Settings) -> None:
    for env_name, settings_attr in _SETTINGS_TO_ENV:
        if os.environ.get(env_name, "").strip():
            continue
        value = getattr(settings, settings_attr, None)
        if isinstance(value, str) and value.strip():
            os.environ[env_name] = value.strip()
