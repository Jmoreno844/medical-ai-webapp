from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.documents.api.callbacks import transcription_complete_notification
from apps.documents.models import Document
from apps.documents.schemas import TranscriptionNotificationIn
from apps.encounters.models import Encounter
from apps.generative_ai.api import start_transcription
from apps.generative_ai.schemas import TranscriptionRequest
from apps.generative_ai.services.transcription_tasks import (
    TranscriptionTaskConfigurationError,
    enqueue_transcription_task,
)
from apps.patients.models import Patient, PatientDoctor
from apps.users.models import User


class _FakeTasksClient:
    def __init__(self):
        self.requests = []

    def queue_path(self, project_id, region, queue_name):
        return f"projects/{project_id}/locations/{region}/queues/{queue_name}"

    def create_task(self, request):
        self.requests.append(request)
        return SimpleNamespace(name="tasks/transcription-123")


class TranscriptionTaskQueueTests(SimpleTestCase):
    @override_settings(
        GCP_PROJECT_ID="vext-stg",
        CLOUD_TASKS_REGION="us-east1",
        TRANSCRIPTION_QUEUE_NAME="audio-transcription-queue",
        TRANSCRIPTION_CLOUD_FUNCTION_URL="https://transcription.example.run.app",
        CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT="cloud-tasks-invoker@vext-stg.iam.gserviceaccount.com",
    )
    def test_enqueue_transcription_task_uses_invoker_service_account(self):
        client = _FakeTasksClient()
        task_name = enqueue_transcription_task(
            {
                "document_id": 42,
                "audio_uri": "gs://bucket/file.webm",
                "auth_token": "jwt",
            },
            task_client=client,
        )

        self.assertEqual(task_name, "tasks/transcription-123")
        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(
            request["parent"],
            "projects/vext-stg/locations/us-east1/queues/audio-transcription-queue",
        )
        oidc_token = request["task"]["http_request"]["oidc_token"]
        self.assertEqual(
            oidc_token["service_account_email"],
            "cloud-tasks-invoker@vext-stg.iam.gserviceaccount.com",
        )
        self.assertEqual(
            oidc_token["audience"],
            "https://transcription.example.run.app",
        )

    @override_settings(
        GCP_PROJECT_ID="vext-stg",
        CLOUD_TASKS_REGION="us-east1",
        TRANSCRIPTION_QUEUE_NAME="audio-transcription-queue",
        TRANSCRIPTION_CLOUD_FUNCTION_URL="not-loaded",
        CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT="",
    )
    def test_enqueue_transcription_task_fails_clearly_when_configuration_missing(self):
        with self.assertRaises(TranscriptionTaskConfigurationError) as ctx:
            enqueue_transcription_task(
                {"document_id": 1}, task_client=_FakeTasksClient()
            )

        self.assertIn("not fully configured", str(ctx.exception))


class TranscriptionFlowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            email="doctor@example.com",
            name="Doc",
            last_name="Tor",
            password="safe-password",
        )
        self.patient = Patient.objects.create(name="Paciente Uno")
        PatientDoctor.objects.create(doctor=self.doctor, patient=self.patient)
        self.encounter = Encounter.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            occurred_at=datetime.now(timezone.utc),
            audio_file_name="encounter_audio/1/audio.webm",
        )
        self.document = Document.objects.create(
            encounter=self.encounter,
            kind="transcription",
            content="",
            doctor=self.doctor,
        )

    @override_settings(
        ENVIRONMENT="stg",
        GCS_BUCKET_NAME="vext-stg-audio",
        GCP_PROJECT_ID="vext-stg",
        CLOUD_TASKS_REGION="us-east1",
        TRANSCRIPTION_QUEUE_NAME="audio-transcription-queue",
        TRANSCRIPTION_CLOUD_FUNCTION_URL="https://transcription.example.run.app",
        CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT="cloud-tasks-invoker@vext-stg.iam.gserviceaccount.com",
        JWT_SECRET_KEY="jwt-secret",
        SECRET_KEY="django-secret",
    )
    @patch(
        "apps.generative_ai.api.enqueue_transcription_task",
        return_value="tasks/transcription-123",
    )
    def test_start_transcription_queues_task_without_marking_encounter_complete(
        self, enqueue_mock
    ):
        request = SimpleNamespace(user=self.doctor)
        payload = TranscriptionRequest(
            encounter_id=self.encounter.id,
            document_id=self.document.id,
        )

        response = start_transcription(request, payload)

        self.assertTrue(response.success)
        self.assertEqual(response.message, "Transcription queued successfully")
        self.encounter.refresh_from_db()
        self.assertFalse(self.encounter.has_been_transcribed)
        enqueue_mock.assert_called_once()

    def test_transcription_complete_callback_marks_encounter_as_transcribed(self):
        payload = TranscriptionNotificationIn(document_id=self.document.id)
        response = transcription_complete_notification(
            request=None,
            payload=payload,
            auth={"document_id": self.document.id, "user_id": self.doctor.id},
        )

        self.assertTrue(response["success"])
        self.encounter.refresh_from_db()
        self.assertTrue(self.encounter.has_been_transcribed)
