from __future__ import annotations

import json
from types import SimpleNamespace

from app.core.config import Settings
from app.integrations.document_generation_tasks import enqueue_document_generation_task


class FakeCloudTasksClient:
    def __init__(self) -> None:
        self.created_task = None

    def queue_path(self, project: str, region: str, queue: str) -> str:
        return f"projects/{project}/locations/{region}/queues/{queue}"

    def create_task(self, *, request: dict):
        self.created_task = request["task"]
        return SimpleNamespace(name="task-name")


def test_document_generation_task_payload_excludes_clinical_content() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    settings.gcp_project_id = "project"
    settings.cloud_tasks_region = "us-east1"
    settings.document_generation_queue_name = "document-generation-queue"
    settings.document_generation_task_target_url = (
        "https://worker/api/v1/internal/document-generation/tasks"
    )
    settings.cloud_tasks_invoker_service_account = "tasks@example.iam.gserviceaccount.com"
    client = FakeCloudTasksClient()

    enqueue_document_generation_task(
        {
            "process_id": "gen_1",
            "doctor_id": 7,
            "new_document_id": 11,
            "context_document_id": 12,
            "transcription_document_id": 13,
            "doctor_template_id": 14,
        },
        settings=settings,
        task_client=client,
    )

    body = json.loads(client.created_task["http_request"]["body"].decode("utf-8"))
    assert set(body) == {
        "process_id",
        "doctor_id",
        "new_document_id",
        "context_document_id",
        "transcription_document_id",
        "doctor_template_id",
    }
    assert "auth_token" not in body
    assert "transcription_document" not in body
    assert client.created_task["http_request"]["url"].endswith("/gen_1")
