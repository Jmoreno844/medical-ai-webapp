"""Cloud Tasks helpers for asynchronous transcription dispatch."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from django.conf import settings
from google.cloud import tasks_v2

logger = logging.getLogger(__name__)


class TranscriptionTaskConfigurationError(RuntimeError):
    """Raised when Cloud Tasks dispatch is selected but not fully configured."""


def is_transcription_queue_configured() -> bool:
    required_values = [
        getattr(settings, "GCP_PROJECT_ID", ""),
        getattr(settings, "CLOUD_TASKS_REGION", ""),
        getattr(settings, "TRANSCRIPTION_QUEUE_NAME", ""),
        getattr(settings, "TRANSCRIPTION_CLOUD_FUNCTION_URL", ""),
        getattr(settings, "CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT", ""),
    ]
    return all(
        bool(str(value).strip()) and str(value).strip() != "not-loaded"
        for value in required_values
    )


def should_use_cloud_tasks() -> bool:
    environment = str(getattr(settings, "ENVIRONMENT", "") or "").strip().lower()
    return (
        environment in {"stg", "staging", "prod", "production"}
        or is_transcription_queue_configured()
    )


def enqueue_transcription_task(
    payload: Mapping[str, Any],
    task_client: tasks_v2.CloudTasksClient | None = None,
) -> str:
    if not is_transcription_queue_configured():
        raise TranscriptionTaskConfigurationError(
            "Cloud Tasks transcription is not fully configured; missing project, region, queue, function URL, or invoker SA"
        )

    client = task_client or tasks_v2.CloudTasksClient()
    project_id = str(settings.GCP_PROJECT_ID).strip()
    region = str(settings.CLOUD_TASKS_REGION).strip()
    queue_name = str(settings.TRANSCRIPTION_QUEUE_NAME).strip()
    target_url = str(settings.TRANSCRIPTION_CLOUD_FUNCTION_URL).strip()
    invoker_sa = str(settings.CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT).strip()

    parent = client.queue_path(project_id, region, queue_name)
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
            "oidc_token": {
                "service_account_email": invoker_sa,
                "audience": target_url,
            },
        }
    }

    response = client.create_task(request={"parent": parent, "task": task})
    logger.info(
        "Queued transcription task for document %s in queue %s",
        payload.get("document_id"),
        queue_name,
    )
    return response.name
