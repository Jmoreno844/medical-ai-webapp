from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.domains.documents.generation_api import _post_document_worker_task_background
from app.integrations.document_pipeline_tasks import enqueue_document_pipeline_task


class FakeCloudTasksClient:
    def __init__(self) -> None:
        self.created_task = None

    def queue_path(self, project: str, region: str, queue: str) -> str:
        return f"projects/{project}/locations/{region}/queues/{queue}"

    def create_task(self, *, request: dict):
        self.created_task = request["task"]
        return SimpleNamespace(name="task-name")


def test_document_pipeline_task_payload_excludes_clinical_content() -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    settings.gcp_project_id = "project"
    settings.cloud_tasks_region = "us-east1"
    settings.document_pipeline_queue_name = "document-pipeline-queue"
    settings.document_pipeline_task_target_url = (
        "https://worker/api/v1/internal/document-pipeline/tasks"
    )
    settings.cloud_tasks_invoker_service_account = "tasks@example.iam.gserviceaccount.com"
    client = FakeCloudTasksClient()

    enqueue_document_pipeline_task(
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


@pytest.mark.asyncio
async def test_local_pipeline_dispatch_failure_publishes_sse_error(monkeypatch) -> None:
    settings = Settings(JWT_SECRET_KEY="test-secret-at-least-32-bytes-long")
    settings.document_pipeline_worker_base_url = "http://localhost:8092"

    published: list[tuple[int, str, dict]] = []

    async def fake_post_json(*args, **kwargs) -> None:
        raise RuntimeError("worker down")

    async def fake_publish_document_event(
        document_id: int,
        event: str,
        payload: dict | None = None,
    ) -> None:
        published.append((document_id, event, payload or {}))

    monkeypatch.setattr(
        "app.domains.documents.generation_api.post_json_async",
        fake_post_json,
    )
    monkeypatch.setattr(
        "app.domains.documents.generation_api.publish_document_event",
        fake_publish_document_event,
    )

    await _post_document_worker_task_background(
        "/api/v1/internal/document-pipeline/tasks/gen_77",
        {
            "process_id": "gen_77",
            "new_document_id": 77,
        },
        settings,
    )

    assert published == [
        (
            77,
            "generation_error",
            {
                "process_id": "gen_77",
                "error": (
                    "No se pudo iniciar la generación del documento. "
                    "Reintente en unos momentos."
                ),
            },
        )
    ]
