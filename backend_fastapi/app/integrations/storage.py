from __future__ import annotations

import json
import logging

import google.auth
from google.auth import impersonated_credentials
from google.cloud import storage
from google.oauth2 import service_account

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _gcs_client_from_adc(settings: Settings) -> storage.Client:
    project = settings.gcp_project_id or None
    return storage.Client(project=project) if project else storage.Client()


def _gcs_client_from_impersonated_adc(settings: Settings) -> storage.Client | None:
    target_principal = (settings.gcp_storage_impersonated_service_account or "").strip()
    if not target_principal or target_principal == "not-loaded":
        return None

    source_credentials, discovered_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if hasattr(source_credentials, "with_quota_project") and settings.gcp_project_id:
        source_credentials = source_credentials.with_quota_project(settings.gcp_project_id)

    credentials = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=target_principal,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=900,
    )
    return storage.Client(
        credentials=credentials,
        project=settings.gcp_project_id or discovered_project,
    )


def get_storage_client(settings: Settings | None = None) -> storage.Client:
    settings = settings or get_settings()
    key_path = (settings.gcp_storage_service_account_key_path or "").strip()
    if settings.environment == "dev" and key_path and key_path != "not-loaded":
        credentials = service_account.Credentials.from_service_account_file(key_path)
        return storage.Client(credentials=credentials)

    impersonated_client = _gcs_client_from_impersonated_adc(settings)
    if impersonated_client is not None:
        return impersonated_client

    raw = (settings.service_account_json or "").strip()
    if not raw or raw == "{}":
        return _gcs_client_from_adc(settings)

    try:
        service_account_info = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SERVICE_ACCOUNT_JSON is not valid JSON; using ADC for GCS")
        return _gcs_client_from_adc(settings)

    if not isinstance(service_account_info, dict) or not service_account_info.get(
        "private_key"
    ):
        return _gcs_client_from_adc(settings)

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )
    return storage.Client(
        credentials=credentials,
        project=service_account_info.get("project_id") or settings.gcp_project_id,
    )

