from __future__ import annotations

import json
from typing import Any, Mapping

from app.core.config import Settings


class ClinicalExtractionTaskConfigurationError(RuntimeError):
    pass


def _is_configured_value(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() != "not-loaded")


def is_clinical_extraction_queue_configured(settings: Settings) -> bool:
    return all(
        _is_configured_value(value)
        for value in (
            settings.gcp_project_id,
            settings.cloud_tasks_region,
            settings.clinical_extraction_queue_name,
            settings.clinical_extraction_task_target_url,
            settings.cloud_tasks_invoker_service_account,
        )
    )


def should_use_clinical_extraction_cloud_tasks(settings: Settings) -> bool:
    environment = settings.environment.strip().lower()
    return environment in {"stg", "staging", "prod", "production"} or (
        is_clinical_extraction_queue_configured(settings)
    )


def enqueue_clinical_extraction_task(
    payload: Mapping[str, Any],
    *,
    settings: Settings,
    task_client: Any | None = None,
) -> str:
    if not is_clinical_extraction_queue_configured(settings):
        raise ClinicalExtractionTaskConfigurationError(
            "Cloud Tasks clinical extraction is not fully configured; missing "
            "project, region, queue, task target URL, or invoker SA"
        )

    try:
        from google.cloud import tasks_v2
    except ImportError as exc:
        raise ClinicalExtractionTaskConfigurationError(
            "google-cloud-tasks is required for clinical extraction task dispatch"
        ) from exc

    session_id = str(payload["session_id"]).strip()
    target_base_url = str(settings.clinical_extraction_task_target_url).strip().rstrip("/")
    target_url = f"{target_base_url}/{session_id}"
    client = task_client or tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        str(settings.gcp_project_id).strip(),
        str(settings.cloud_tasks_region).strip(),
        str(settings.clinical_extraction_queue_name).strip(),
    )
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(dict(payload)).encode("utf-8"),
            "oidc_token": {
                "service_account_email": str(
                    settings.cloud_tasks_invoker_service_account
                ).strip(),
                "audience": target_url,
            },
        }
    }
    response = client.create_task(request={"parent": parent, "task": task})
    return response.name
