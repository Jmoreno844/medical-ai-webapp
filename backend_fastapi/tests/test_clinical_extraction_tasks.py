from __future__ import annotations

from types import SimpleNamespace

from app.integrations.clinical_extraction_tasks import (
    enqueue_clinical_extraction_task,
    is_clinical_extraction_queue_configured,
)


class FakeClient:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def queue_path(self, project: str, region: str, queue: str) -> str:
        return f"projects/{project}/locations/{region}/queues/{queue}"

    def create_task(self, request: dict) -> SimpleNamespace:
        self.created.append(request)
        return SimpleNamespace(name="task-name")


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        gcp_project_id="project",
        cloud_tasks_region="us-east1",
        clinical_extraction_queue_name="clinical-extraction",
        clinical_extraction_task_target_url=(
            "https://worker/api/v1/internal/clinical-extraction/tasks"
        ),
        cloud_tasks_invoker_service_account="tasks@example.iam.gserviceaccount.com",
    )


def test_clinical_extraction_queue_configuration() -> None:
    assert is_clinical_extraction_queue_configured(_settings()) is True  # type: ignore[arg-type]


def test_enqueue_clinical_extraction_task_builds_session_url() -> None:
    client = FakeClient()
    task_name = enqueue_clinical_extraction_task(
        {"session_id": "sess-1"},
        settings=_settings(),  # type: ignore[arg-type]
        task_client=client,
    )

    assert task_name == "task-name"
    task = client.created[0]["task"]["http_request"]
    assert task["url"].endswith("/sess-1")
    assert task["oidc_token"]["audience"] == task["url"]
