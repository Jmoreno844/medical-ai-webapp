"""Google Cloud Storage client for encounter audio."""

import json
import logging

import google.auth
from django.conf import settings
from google.auth import impersonated_credentials
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


def _gcs_client_from_adc() -> storage.Client:
    """Use workload identity (Cloud Run SA, gcloud ADC locally, etc.)."""
    project = getattr(settings, "GCP_PROJECT_ID", None) or None
    client = storage.Client(project=project) if project else storage.Client()
    logger.debug("GCS client using application default credentials")
    return client


def _gcs_client_from_impersonated_adc() -> storage.Client | None:
    """Use local ADC to impersonate a dedicated signer service account."""
    target_principal = (
        getattr(settings, "GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT", "") or ""
    ).strip()
    if not target_principal or target_principal == "not-loaded":
        return None

    project = getattr(settings, "GCP_PROJECT_ID", None) or None
    source_credentials, discovered_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if hasattr(source_credentials, "with_quota_project") and project:
        source_credentials = source_credentials.with_quota_project(project)

    credentials = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=target_principal,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=900,
    )
    logger.debug(
        "GCS client using impersonated ADC for service account %s", target_principal
    )
    return storage.Client(
        credentials=credentials,
        project=project or discovered_project,
    )


def get_storage_client() -> storage.Client:
    """
    Return a GCS client.

    - ``ENVIRONMENT == dev`` (``config.settings.develop``): JSON key file path
      ``GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH``; otherwise local ADC may
      impersonate ``GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT``.
    - Otherwise: if ``SERVICE_ACCOUNT_JSON`` is empty or not a full key payload,
      use ADC (Cloud Run service account on GCP; optional JSON key locally).
    """
    if getattr(settings, "ENVIRONMENT", "dev") == "dev":
        key_path = getattr(settings, "GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH", "")
        if key_path and key_path != "not-loaded":
            credentials = service_account.Credentials.from_service_account_file(
                key_path
            )
            return storage.Client(credentials=credentials)

        impersonated_client = _gcs_client_from_impersonated_adc()
        if impersonated_client is not None:
            return impersonated_client

        logger.warning(
            "GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH is not loaded and "
            "GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT is empty; falling back "
            "to plain ADC in dev"
        )

    raw = (getattr(settings, "SERVICE_ACCOUNT_JSON", None) or "").strip()
    if not raw or raw == "{}":
        return _gcs_client_from_adc()

    try:
        service_account_info = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SERVICE_ACCOUNT_JSON is not valid JSON; using ADC for GCS")
        return _gcs_client_from_adc()

    if not isinstance(service_account_info, dict) or not service_account_info.get(
        "private_key"
    ):
        return _gcs_client_from_adc()

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )
    return storage.Client(
        credentials=credentials,
        project=service_account_info.get("project_id")
        or getattr(settings, "GCP_PROJECT_ID", None),
    )
