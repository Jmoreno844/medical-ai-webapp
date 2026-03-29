"""Google Cloud Storage client for encounter audio."""

import json

from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account


def get_storage_client() -> storage.Client:
    """Return a GCS client using dev file credentials or JSON from settings."""
    if getattr(settings, "ENVIRONMENT", "dev") == "dev":
        credentials = service_account.Credentials.from_service_account_file(
            settings.GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH
        )
        return storage.Client(credentials=credentials)
    service_account_info = json.loads(settings.SERVICE_ACCOUNT_JSON)
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )
    return storage.Client(credentials=credentials)
