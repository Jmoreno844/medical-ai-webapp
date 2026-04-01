"""Google Cloud Storage client for encounter audio."""

import json
import logging

from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


def _gcs_client_from_adc() -> storage.Client:
    """Use workload identity (Cloud Run SA, gcloud ADC locally, etc.)."""
    project = getattr(settings, "GCP_PROJECT_ID", None) or None
    client = storage.Client(project=project) if project else storage.Client()
    logger.debug("GCS client using application default credentials")
    return client


def get_storage_client() -> storage.Client:
    """
    Return a GCS client.

    - ``ENVIRONMENT == dev`` (``config.settings.develop``): JSON key file path
      ``GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH``.
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
        logger.warning("GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH is not loaded, falling back to ADC in dev")

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
