from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from ninja.errors import HttpError

from apps.copilot.api import (
    apply_copilot_patch_set,
    create_copilot_message,
    create_copilot_session,
    finalize_copilot_patch_set_review,
    get_copilot_run,
    list_copilot_patches,
    list_copilot_patch_sets,
    review_copilot_patch,
    stream_copilot_run,
)
from apps.copilot.services.patch_apply import CopilotPatchConflictError
from apps.copilot.services.patch_apply import apply_copilot_patch
from apps.copilot.services.client import CopilotAgentClient
from apps.copilot.services.patch_sets import (
    _apply_patches_to_content,
    _detect_internal_conflicts,
    _resolve_patch_against_document,
    CopilotPatchSetConflictError,
    content_hash,
)
from apps.copilot.internal_tools_api import (
    list_encounter_documents_tool,
    list_open_documents_tool,
    read_document_tool,
    search_documents_tool,
)


class CopilotBrokerTests(SimpleTestCase):
    def setUp(self):
        self.doctor = SimpleNamespace(id=7)
        self.other_doctor = SimpleNamespace(id=9)
        self.encounter = SimpleNamespace(id=12, doctor_id=self.doctor.id)
        self.thread_id = (
            f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:chat:"
            "11111111-1111-4111-8111-111111111111"
        )
        self.workspace_index = {
            "encounter_id": str(self.encounter.id),
            "workspace_version": "v1",
            "active_document_id": "99",
            "open_document_ids": ["99"],
            "documents": [
                {
                    "document_id": "99",
                    "type": "note",
                    "title": "Note",
                    "status": "draft",
                    "source": "user",
                    "ai_readable": True,
                    "ai_writable": True,
                    "version": 1,
                    "updated_at": "2026-04-02T10:00:00Z",
                    "is_active": True,
                    "is_open": True,
                    "has_dirty_draft": False,
                    "has_streaming_state": False,
                    "hidden_from_agent": False,
                    "pinned_for_agent": False,
                }
            ],
        }

    def test_create_session_returns_new_scoped_thread_id(self):
        request = SimpleNamespace(user=self.doctor)

        with (
            patch(
                "apps.copilot.api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.services.threads.uuid.uuid4",
                side_effect=[
                    "11111111-1111-4111-8111-111111111111",
                    "22222222-2222-4222-8222-222222222222",
                ],
            ),
        ):
            response = create_copilot_session(
                request,
                SimpleNamespace(encounter_id=self.encounter.id),
            )
            second_response = create_copilot_session(
                request,
                SimpleNamespace(encounter_id=self.encounter.id),
            )

        self.assertEqual(
            response["thread_id"],
            f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:chat:11111111-1111-4111-8111-111111111111",
        )
        self.assertEqual(
            second_response["thread_id"],
            f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:chat:22222222-2222-4222-8222-222222222222",
        )
        self.assertEqual(response["capability"], "read_only")

    def test_create_message_persists_run(self):
        request = SimpleNamespace(user=self.doctor)
        payload = SimpleNamespace(
            encounter_id=self.encounter.id,
            thread_id=self.thread_id,
            user_message="Hazme un resumen",
            workspace_index=SimpleNamespace(
                model_dump=lambda mode="python": self.workspace_index
            ),
            active_document_id="99",
            selected_document_ids=["99"],
        )

        with (
            patch(
                "apps.copilot.api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.api.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.copilot.api.CopilotAgentClient.create_run",
                return_value={
                    "run": {
                        "run_id": "run-123",
                        "thread_id": self.thread_id,
                        "status": "completed",
                        "intent": "answer_question",
                        "requires_human_review": False,
                        "final_response": "Resumen listo",
                        "trace_metadata": {},
                    },
                    "events": [],
                },
            ) as agent_create_run_mock,
            patch(
                "apps.copilot.api.CopilotRun.objects.create",
                return_value=SimpleNamespace(
                    run_id="run-123",
                    thread_id=self.thread_id,
                    status="completed",
                    intent="answer_question",
                    requires_human_review=False,
                ),
            ) as create_run_mock,
        ):
            response = create_copilot_message(request, payload)

        agent_create_run_mock.assert_called_once()
        self.assertEqual(
            agent_create_run_mock.call_args.args[0]["thread_id"],
            self.thread_id,
        )
        create_run_mock.assert_called_once()
        self.assertEqual(response["run_id"], "run-123")
        self.assertEqual(response["status"], "completed")

    def test_create_message_persists_patch_set_preview(self):
        request = SimpleNamespace(user=self.doctor)
        payload = SimpleNamespace(
            encounter_id=self.encounter.id,
            thread_id=self.thread_id,
            user_message="Actualiza la nota",
            workspace_index=SimpleNamespace(
                model_dump=lambda mode="python": self.workspace_index
            ),
            active_document_id="99",
            selected_document_ids=["99"],
        )
        run_instance = SimpleNamespace(
            run_id="run-456",
            thread_id=self.thread_id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
        )

        with (
            patch(
                "apps.copilot.api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.api.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.copilot.api.CopilotAgentClient.create_run",
                return_value={
                    "run": {
                        "run_id": "run-456",
                        "thread_id": run_instance.thread_id,
                        "status": "waiting_review",
                        "intent": "edit_document",
                        "requires_human_review": True,
                        "active_patch_set_id": "pset-123",
                        "patch_set_preview": {
                            "patch_set_id": "pset-123",
                            "target_document_id": "99",
                            "base_version": 3,
                            "base_hash": "hash-123",
                            "target_document_title": "Note",
                            "target_selection_reason": "title_family_match:clinical_note; score=72",
                            "rationale": "Actualizar el documento activo",
                            "document_preview_after": "## Propuesta",
                            "patches": [
                                {
                                    "patch_id": "patch-123",
                                    "patch_type": "replace_span",
                                    "operation_type": "rewrite_document",
                                    "order_index": 0,
                                    "anchor": {"exactText": "Texto"},
                                    "content_preview": "## Propuesta",
                                }
                            ],
                        },
                        "trace_metadata": {},
                    },
                    "events": [],
                },
            ),
            patch(
                "apps.copilot.api.CopilotRun.objects.create",
                return_value=run_instance,
            ),
            patch(
                "apps.copilot.api.get_object_or_404",
                side_effect=[SimpleNamespace(id=99, encounter_id=12, doctor_id=7)],
            ),
            patch(
                "apps.copilot.api.persist_patch_set_preview",
                return_value=Mock(),
            ) as persist_patch_set_mock,
        ):
            response = create_copilot_message(request, payload)

        persist_patch_set_mock.assert_called_once()
        self.assertEqual(response["status"], "waiting_review")
        self.assertEqual(response["active_patch_set_id"], "pset-123")

    def test_create_message_rejects_inconsistent_edit_run_from_agent(self):
        request = SimpleNamespace(user=self.doctor)
        payload = SimpleNamespace(
            encounter_id=self.encounter.id,
            thread_id=self.thread_id,
            user_message="Actualiza la nota",
            workspace_index=SimpleNamespace(
                model_dump=lambda mode="python": self.workspace_index
            ),
            active_document_id="99",
            selected_document_ids=["99"],
        )

        with (
            patch(
                "apps.copilot.api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.api.CopilotAgentClient.create_run",
                return_value={
                    "run": {
                        "run_id": "run-456",
                        "thread_id": self.thread_id,
                        "status": "completed",
                        "intent": "edit_document",
                        "requires_human_review": False,
                        "patch_set_preview": {
                            "patch_set_id": "pset-123",
                            "target_document_id": "99",
                            "base_version": 3,
                            "base_hash": "hash-123",
                            "target_document_title": "Note",
                            "target_selection_reason": "title_family_match:clinical_note; score=72",
                            "patches": [
                                {
                                    "patch_id": "patch-123",
                                    "patch_type": "replace_span",
                                    "operation_type": "rewrite_document",
                                    "order_index": 0,
                                    "anchor": {"exactText": "Texto"},
                                    "content_preview": "## Propuesta",
                                }
                            ],
                        },
                        "trace_metadata": {},
                    },
                    "events": [],
                },
            ),
        ):
            with self.assertRaises(HttpError) as ctx:
                create_copilot_message(request, payload)

        self.assertEqual(ctx.exception.status_code, 502)


class CopilotClientTests(SimpleTestCase):
    def setUp(self):
        self.doctor = SimpleNamespace(id=7)
        self.other_doctor = SimpleNamespace(id=9)
        self.encounter = SimpleNamespace(id=12, doctor_id=self.doctor.id)
        self.thread_id = (
            f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:chat:"
            "11111111-1111-4111-8111-111111111111"
        )
        self.workspace_index = {
            "encounter_id": str(self.encounter.id),
            "workspace_version": "v1",
            "active_document_id": "99",
            "open_document_ids": ["99"],
            "documents": [
                {
                    "document_id": "99",
                    "type": "note",
                    "title": "Note",
                    "status": "draft",
                    "source": "user",
                    "ai_readable": True,
                    "ai_writable": True,
                    "version": 1,
                    "updated_at": "2026-04-02T10:00:00Z",
                    "is_active": True,
                    "is_open": True,
                    "has_dirty_draft": False,
                    "has_streaming_state": False,
                    "hidden_from_agent": False,
                    "pinned_for_agent": False,
                }
            ],
        }

    @override_settings(
        COPILOT_AGENT_BASE_URL="http://localhost:8090",
        COPILOT_AGENT_TIMEOUT_SECONDS=30,
    )
    def test_client_enforces_timeout_floor_for_edit_runs(self):
        client = CopilotAgentClient()

        self.assertEqual(client.timeout, 60.0)

    def test_create_message_rejects_other_doctor(self):
        request = SimpleNamespace(user=self.other_doctor)
        payload = SimpleNamespace(
            encounter_id=self.encounter.id,
            thread_id=self.thread_id,
            user_message="Resumen",
            workspace_index=SimpleNamespace(
                model_dump=lambda mode="python": self.workspace_index
            ),
            active_document_id="99",
            selected_document_ids=["99"],
        )

        with patch(
            "apps.copilot.api._get_owned_encounter",
            side_effect=HttpError(
                403, "No tienes permiso para acceder a este encuentro"
            ),
        ):
            with self.assertRaises(HttpError) as ctx:
                create_copilot_message(request, payload)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_message_rejects_thread_id_from_other_scope(self):
        request = SimpleNamespace(user=self.doctor)
        payload = SimpleNamespace(
            encounter_id=self.encounter.id,
            thread_id="copilot:encounter:99:doctor:7:chat:11111111-1111-4111-8111-111111111111",
            user_message="Resumen",
            workspace_index=SimpleNamespace(
                model_dump=lambda mode="python": self.workspace_index
            ),
            active_document_id="99",
            selected_document_ids=["99"],
        )

        with patch(
            "apps.copilot.api._get_owned_encounter",
            return_value=self.encounter,
        ):
            with self.assertRaises(HttpError) as ctx:
                create_copilot_message(request, payload)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_run_syncs_remote_status(self):
        run = Mock(
            run_id="run-123",
            thread_id=(
                f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:"
                "chat:11111111-1111-4111-8111-111111111111"
            ),
            doctor_id=self.doctor.id,
            status="created",
            intent=None,
            requires_human_review=False,
        )
        request = SimpleNamespace(user=self.doctor)

        with (
            patch("apps.copilot.api.get_object_or_404", return_value=run),
            patch(
                "apps.copilot.api.CopilotAgentClient.get_run",
                return_value={
                    "run_id": run.run_id,
                    "thread_id": run.thread_id,
                    "status": "completed",
                    "intent": "answer_question",
                    "requires_human_review": False,
                    "final_response": "Resumen listo",
                    "trace_metadata": {},
                },
            ),
        ):
            response = get_copilot_run(request, run.run_id)

        run.save.assert_called_once()
        self.assertEqual(response["status"], "completed")

    def test_stream_replays_remote_events(self):
        run = Mock(
            run_id="run-123",
            thread_id=(
                f"copilot:encounter:{self.encounter.id}:doctor:{self.doctor.id}:"
                "chat:11111111-1111-4111-8111-111111111111"
            ),
            doctor_id=self.doctor.id,
            status="created",
        )
        request = SimpleNamespace(user=self.doctor)

        with (
            patch("apps.copilot.api.get_object_or_404", return_value=run),
            patch(
                "apps.copilot.api.CopilotAgentClient.list_run_events",
                return_value={
                    "events": [
                        {
                            "sequence": 1,
                            "event": "response_chunk",
                            "run_id": "run-123",
                            "thread_id": run.thread_id,
                            "created_at": "2026-04-02T10:00:00Z",
                            "payload": {"content": "Resumen listo"},
                        }
                    ],
                    "status": "completed",
                    "next_after_sequence": 1,
                    "done": True,
                },
            ),
        ):
            response = stream_copilot_run(request, "run-123")
            chunks = b"".join(response.streaming_content).decode()

        run.save.assert_called_once()
        self.assertIn("event: response_chunk", chunks)
        self.assertIn("Resumen listo", chunks)

    def test_list_patches_returns_only_owned_run_patches(self):
        request = SimpleNamespace(user=self.doctor)
        run = SimpleNamespace(run_id="run-123", doctor_id=self.doctor.id)
        patch_instance = SimpleNamespace(
            patch_id="patch-123",
            patch_set_id="pset-123",
            patch_set=SimpleNamespace(patch_set_id="pset-123"),
            run=SimpleNamespace(run_id="run-123"),
            target_document_id=99,
            base_version=3,
            order_index=0,
            patch_type="replace_span",
            operation_type="rewrite_document",
            anchor={},
            expected_hash=None,
            old_text=None,
            new_text=None,
            resolved_start=None,
            resolved_end=None,
            confidence=None,
            conflict_reason=None,
            replacement_text="## Propuesta",
            inserted_text=None,
            document_preview_after=None,
            content_preview="## Propuesta",
            rationale="Actualizar",
            source_context_document_ids=["12"],
            target_document_title="Nota",
            target_selection_reason="title_family_match:clinical_note; score=72",
            status="pending",
            review_comment=None,
            created_at="2026-04-02T10:00:00Z",
            updated_at="2026-04-02T10:00:00Z",
        )

        with (
            patch("apps.copilot.api.get_object_or_404", return_value=run),
            patch(
                "apps.copilot.api.CopilotPatch.objects.filter",
                return_value=SimpleNamespace(
                    select_related=lambda *args, **kwargs: [patch_instance]
                ),
            ),
        ):
            response = list_copilot_patches(request, "run-123")

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["patch_id"], "patch-123")

    def test_review_patch_reject_updates_patch_status(self):
        request = SimpleNamespace(user=self.doctor)
        run = Mock(
            run_id="run-123",
            doctor_id=self.doctor.id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
        )
        patch_instance = Mock(
            patch_id="patch-123",
            status="pending",
        )
        payload = SimpleNamespace(
            patch_id="patch-123",
            decision="reject",
            comment="No aplicar",
        )
        patch_set = SimpleNamespace(
            patch_set_id="pset-123",
            patches=SimpleNamespace(count=lambda: 1),
        )

        with (
            patch(
                "apps.copilot.api.get_object_or_404",
                side_effect=[run, patch_instance],
            ),
            patch(
                "apps.copilot.api.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.copilot.api.ensure_patch_set_for_legacy_patch",
                return_value=patch_set,
            ),
            patch(
                "apps.copilot.api.reject_patch",
            ),
            patch(
                "apps.copilot.api.CopilotAgentClient.resume_run",
                return_value={
                    "run_id": "run-123",
                    "thread_id": "copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
                    "status": "completed",
                    "intent": "edit_document",
                    "requires_human_review": False,
                    "active_patch_set_id": None,
                    "final_response": "Patch rechazado",
                    "trace_metadata": {},
                },
            ),
        ):
            response = review_copilot_patch(request, "run-123", payload)

        run.save.assert_called_once()
        self.assertEqual(response["status"], "completed")

    def test_review_patch_approve_applies_document_and_returns_metadata(self):
        request = SimpleNamespace(user=self.doctor)
        run = Mock(
            run_id="run-123",
            doctor_id=self.doctor.id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
        )
        patch_instance = Mock(
            patch_id="patch-123",
            status="pending",
        )
        payload = SimpleNamespace(
            patch_id="patch-123",
            decision="approve",
            comment="Aplicar",
            document_version=3,
        )
        patch_set = SimpleNamespace(
            patch_set_id="pset-123",
            patches=SimpleNamespace(count=lambda: 1),
        )

        with (
            patch(
                "apps.copilot.api.get_object_or_404",
                side_effect=[run, patch_instance],
            ),
            patch(
                "apps.copilot.api.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.copilot.api.ensure_patch_set_for_legacy_patch",
                return_value=patch_set,
            ),
            patch(
                "apps.copilot.api.accept_patch",
            ),
            patch(
                "apps.copilot.api.apply_copilot_patch",
                return_value=SimpleNamespace(
                    patch_id="patch-123",
                    document_id="99",
                    content="Contenido aplicado",
                    applied_version=4,
                    stale_patch_ids=["patch-old"],
                ),
            ) as apply_patch_mock,
            patch(
                "apps.copilot.api.CopilotAgentClient.resume_run",
                return_value={
                    "run_id": "run-123",
                    "thread_id": "copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
                    "status": "completed",
                    "intent": "edit_document",
                    "requires_human_review": False,
                    "active_patch_set_id": None,
                    "applied_patch_set_id": "pset-123",
                    "final_response": "Patch aplicado",
                    "applied_patch_id": "patch-123",
                    "applied_document_id": "99",
                    "applied_content": "Contenido aplicado",
                    "applied_version": 4,
                    "trace_metadata": {
                        "applied_patch_id": "patch-123",
                        "applied_document_id": "99",
                    },
                },
            ) as resume_run_mock,
        ):
            response = review_copilot_patch(request, "run-123", payload)

        apply_patch_mock.assert_called_once_with(
            patch=patch_instance,
            document_version=3,
            review_comment="Aplicar",
        )
        resume_run_mock.assert_called_once()
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["applied_patch_id"], "patch-123")
        self.assertEqual(response["applied_document_id"], "99")
        self.assertEqual(response["applied_content"], "Contenido aplicado")
        self.assertEqual(response["applied_version"], 4)

    def test_review_patch_conflict_marks_patch_stale(self):
        request = SimpleNamespace(user=self.doctor)
        run = Mock(
            run_id="run-123",
            doctor_id=self.doctor.id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
        )
        patch_instance = Mock(
            patch_id="patch-123",
            status="pending",
        )
        payload = SimpleNamespace(
            patch_id="patch-123",
            decision="approve",
            comment=None,
            document_version=9,
        )

        with (
            patch(
                "apps.copilot.api.get_object_or_404",
                side_effect=[run, patch_instance],
            ),
            patch(
                "apps.copilot.api.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.copilot.api.apply_copilot_patch",
                side_effect=CopilotPatchConflictError(
                    "El patch quedo stale porque el documento cambio desde que se propuso"
                ),
            ),
            patch("apps.copilot.api.CopilotAgentClient.resume_run") as resume_run_mock,
        ):
            with self.assertRaises(HttpError) as ctx:
                review_copilot_patch(request, "run-123", payload)

        resume_run_mock.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_list_patch_sets_returns_serialized_patch_sets(self):
        request = SimpleNamespace(user=self.doctor)
        run = SimpleNamespace(run_id="run-123", doctor_id=self.doctor.id)
        patch_set = SimpleNamespace(
            patch_set_id="pset-123",
            run=SimpleNamespace(run_id="run-123"),
            target_document_id=99,
            base_version=3,
            base_hash="hash-123",
            rationale="Actualizar plan",
            source_context_document_ids=["12"],
            target_document_title="Nota clínica",
            target_selection_reason="title_family_match:clinical_note",
            document_preview_after="## Propuesta",
            status="pending",
            review_comment=None,
            created_at="2026-04-02T10:00:00Z",
            updated_at="2026-04-02T10:00:00Z",
            patches=SimpleNamespace(
                select_related=lambda *args, **kwargs: SimpleNamespace(
                    order_by=lambda *a, **k: []
                )
            ),
        )

        with (
            patch("apps.copilot.api.get_object_or_404", return_value=run),
            patch(
                "apps.copilot.api.CopilotPatch.objects.filter",
                return_value=[],
            ),
            patch(
                "apps.copilot.api.CopilotPatchSet.objects.filter",
                return_value=SimpleNamespace(
                    select_related=lambda *args, **kwargs: [patch_set]
                ),
            ),
        ):
            response = list_copilot_patch_sets(request, "run-123")

        self.assertEqual(response[0]["patch_set_id"], "pset-123")

    def test_apply_patch_set_endpoint_resumes_agent_after_apply(self):
        request = SimpleNamespace(user=self.doctor)
        run = SimpleNamespace(
            run_id="run-123",
            thread_id="copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
            doctor_id=self.doctor.id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
            save=Mock(),
        )
        pending_qs = Mock()
        pending_qs.exists.return_value = False
        accepted_qs = Mock()
        accepted_qs.exists.return_value = True
        patch_set = SimpleNamespace(
            patch_set_id="pset-123",
            run=run,
            doctor_id=self.doctor.id,
            patches=SimpleNamespace(
                filter=lambda **kwargs: (
                    pending_qs
                    if kwargs == {"status": "pending"}
                    else accepted_qs
                    if kwargs == {"status": "accepted"}
                    else Mock()
                )
            ),
        )

        with (
            patch(
                "apps.copilot.api._get_owned_patch_set",
                return_value=patch_set,
            ),
            patch(
                "apps.copilot.api.apply_accepted_patch_set",
                return_value=SimpleNamespace(
                    patch_set_id="pset-123",
                    document_id="99",
                    content="Contenido aplicado",
                    applied_version=4,
                    applied_patch_ids=["patch-1"],
                    stale_patch_set_ids=["pset-old"],
                    stale_patch_ids=["patch-old"],
                ),
            ),
            patch(
                "apps.copilot.api.CopilotAgentClient.resume_run",
                return_value={
                    "run_id": "run-123",
                    "thread_id": "copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
                    "status": "completed",
                    "intent": "edit_document",
                    "requires_human_review": False,
                    "active_patch_set_id": None,
                    "applied_patch_set_id": "pset-123",
                    "applied_patch_id": "patch-1",
                    "applied_document_id": "99",
                    "applied_content": "Contenido aplicado",
                    "applied_version": 4,
                    "trace_metadata": {"applied_patch_set_id": "pset-123"},
                },
            ),
        ):
            response = apply_copilot_patch_set(
                request,
                "pset-123",
                SimpleNamespace(comment="Aplicar", document_version=3),
            )

        self.assertEqual(response["applied_patch_set_id"], "pset-123")
        self.assertEqual(response["applied_document_id"], "99")

    def test_finalize_patch_set_review_rejects_when_no_accepted_patches_remain(self):
        request = SimpleNamespace(user=self.doctor)
        run = SimpleNamespace(
            run_id="run-123",
            thread_id="copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
            doctor_id=self.doctor.id,
            status="waiting_review",
            intent="edit_document",
            requires_human_review=True,
            save=Mock(),
        )
        pending_qs = Mock()
        pending_qs.exists.return_value = False
        accepted_qs = Mock()
        accepted_qs.exists.return_value = False
        patch_set = SimpleNamespace(
            patch_set_id="pset-123",
            run=run,
            doctor_id=self.doctor.id,
            patches=SimpleNamespace(
                filter=lambda **kwargs: (
                    pending_qs
                    if kwargs == {"status": "pending"}
                    else accepted_qs
                    if kwargs == {"status": "accepted"}
                    else Mock()
                )
            ),
        )

        with (
            patch(
                "apps.copilot.api._get_owned_patch_set",
                return_value=patch_set,
            ),
            patch(
                "apps.copilot.api.apply_accepted_patch_set",
            ) as apply_mock,
            patch(
                "apps.copilot.api.CopilotAgentClient.resume_run",
                return_value={
                    "run_id": "run-123",
                    "thread_id": "copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111",
                    "status": "completed",
                    "intent": "edit_document",
                    "requires_human_review": False,
                    "active_patch_set_id": None,
                    "final_response": "Patch rechazado",
                    "trace_metadata": {},
                },
            ) as resume_mock,
        ):
            response = finalize_copilot_patch_set_review(
                request,
                "pset-123",
                SimpleNamespace(comment="No aplicar", document_version=3),
            )

        apply_mock.assert_not_called()
        resume_mock.assert_called_once()
        self.assertEqual(
            resume_mock.call_args.args[1]["review_result"],
            "reject",
        )
        self.assertEqual(response["status"], "completed")


class _WorkspaceDocumentStub:
    def __init__(self, **data):
        self.__dict__.update(data)
        self._data = data

    def model_dump(self, mode="python"):
        return self._data


class _FakeDocumentQuerySet(list):
    def filter(self, **kwargs):
        query = kwargs.get("content__icontains", "").lower()
        return _FakeDocumentQuerySet(
            [
                document
                for document in self
                if query in getattr(document, "content", "").lower()
            ]
        )


class CopilotInternalToolsTests(SimpleTestCase):
    def setUp(self):
        self.thread_id = (
            "copilot:encounter:12:doctor:7:chat:11111111-1111-4111-8111-111111111111"
        )
        self.request = SimpleNamespace(
            auth={
                "purpose": "copilot_internal_tools",
                "run_id": "run-123",
                "thread_id": self.thread_id,
                "encounter_id": "12",
                "user_id": "7",
            }
        )
        self.encounter = SimpleNamespace(
            id=12,
            doctor_id=7,
            encounter_name="Encuentro demo",
            occurred_at=None,
            has_been_transcribed=True,
            patient_id=None,
            patient=None,
        )

    def test_list_open_documents_filters_hidden_and_non_readable(self):
        payload = SimpleNamespace(
            run_id="run-123",
            thread_id=self.thread_id,
            encounter_id=12,
            user_id=7,
            workspace_index=SimpleNamespace(
                open_document_ids=["99", "100", "101"],
                documents=[
                    _WorkspaceDocumentStub(
                        document_id="99",
                        title="Nota",
                        type="note",
                        status="draft",
                        source="user",
                        updated_at="2026-04-02T10:00:00Z",
                        is_active=True,
                        is_open=True,
                        ai_readable=True,
                        hidden_from_agent=False,
                        pinned_for_agent=False,
                    ),
                    _WorkspaceDocumentStub(
                        document_id="100",
                        title="Oculto",
                        type="note",
                        status="draft",
                        source="user",
                        updated_at="2026-04-02T10:00:00Z",
                        is_active=False,
                        is_open=True,
                        ai_readable=True,
                        hidden_from_agent=True,
                        pinned_for_agent=False,
                    ),
                    _WorkspaceDocumentStub(
                        document_id="101",
                        title="No legible",
                        type="transcription",
                        status="read_only",
                        source="transcription",
                        updated_at="2026-04-02T10:00:00Z",
                        is_active=False,
                        is_open=True,
                        ai_readable=False,
                        hidden_from_agent=False,
                        pinned_for_agent=False,
                    ),
                ],
            ),
        )

        with patch(
            "apps.copilot.internal_tools_api._get_owned_encounter",
            return_value=self.encounter,
        ):
            response = list_open_documents_tool(self.request, payload)

        self.assertEqual(
            [document.document_id for document in response["documents"]], ["99"]
        )

    def test_read_document_tool_returns_content_for_full_mode(self):
        payload = SimpleNamespace(
            run_id="run-123",
            thread_id=self.thread_id,
            encounter_id=12,
            user_id=7,
            document_id=99,
            mode="full",
        )
        document = SimpleNamespace(
            id=99,
            encounter_id=12,
            doctor_id=7,
            kind="note",
            doctor_template=None,
            content="Paciente con dolor abdominal de varios dias y mejoria parcial.",
            created_on=SimpleNamespace(isoformat=lambda: "2026-04-02T10:00:00Z"),
        )

        with patch(
            "apps.copilot.internal_tools_api._get_owned_document",
            return_value=document,
        ):
            response = read_document_tool(self.request, payload)

        self.assertEqual(response["document_id"], "99")
        self.assertEqual(response["mode"], "full")
        self.assertIn("dolor abdominal", response["content"])

    def test_list_encounter_documents_marks_only_transcriptions_read_only(self):
        payload = SimpleNamespace(
            run_id="run-123",
            thread_id=self.thread_id,
            encounter_id=12,
            user_id=7,
        )
        documents = [
            SimpleNamespace(
                id=10,
                kind="note",
                doctor_template=None,
                content="Nota editable.",
                created_on=SimpleNamespace(isoformat=lambda: "2026-04-02T10:00:00Z"),
            ),
            SimpleNamespace(
                id=11,
                kind="context",
                doctor_template=None,
                content="Contexto editable.",
                created_on=SimpleNamespace(isoformat=lambda: "2026-04-02T11:00:00Z"),
            ),
            SimpleNamespace(
                id=12,
                kind="transcription",
                doctor_template=None,
                content="Transcripcion solo lectura.",
                created_on=SimpleNamespace(isoformat=lambda: "2026-04-02T12:00:00Z"),
            ),
        ]

        with (
            patch(
                "apps.copilot.internal_tools_api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.internal_tools_api._get_encounter_documents",
                return_value=documents,
            ),
        ):
            response = list_encounter_documents_tool(self.request, payload)

        writable_by_id = {
            document.document_id: document.ai_writable
            for document in response["documents"]
        }
        self.assertEqual(writable_by_id, {"10": True, "11": True, "12": False})

    def test_search_documents_tool_limits_results_to_owned_encounter(self):
        payload = SimpleNamespace(
            run_id="run-123",
            thread_id=self.thread_id,
            encounter_id=12,
            user_id=7,
            query="dolor",
            max_results=2,
        )
        documents = _FakeDocumentQuerySet(
            [
                SimpleNamespace(
                    id=10,
                    kind="note",
                    doctor_template=None,
                    content="Dolor lumbar con irradiacion leve.",
                    created_on=SimpleNamespace(
                        isoformat=lambda: "2026-04-02T10:00:00Z"
                    ),
                ),
                SimpleNamespace(
                    id=11,
                    kind="context",
                    doctor_template=None,
                    content="Dolor abdominal posterior a comida.",
                    created_on=SimpleNamespace(
                        isoformat=lambda: "2026-04-02T11:00:00Z"
                    ),
                ),
                SimpleNamespace(
                    id=12,
                    kind="note",
                    doctor_template=None,
                    content="Sin coincidencias relevantes.",
                    created_on=SimpleNamespace(
                        isoformat=lambda: "2026-04-02T12:00:00Z"
                    ),
                ),
            ]
        )

        with (
            patch(
                "apps.copilot.internal_tools_api._get_owned_encounter",
                return_value=self.encounter,
            ),
            patch(
                "apps.copilot.internal_tools_api._get_encounter_documents",
                return_value=documents,
            ),
        ):
            response = search_documents_tool(self.request, payload)

        self.assertEqual(response["query"], "dolor")
        self.assertEqual(len(response["matches"]), 2)
        self.assertEqual(response["matches"][0].document_id, "10")
        self.assertIn("score", response["matches"][0].model_dump())


class CopilotPatchApplyServiceTests(SimpleTestCase):
    def test_apply_copilot_patch_wraps_patch_set_apply(self):
        patch_instance = Mock(
            patch_id="patch-123",
            status="pending",
        )
        patch_set = Mock()

        with (
            patch(
                "apps.copilot.services.patch_apply.ensure_patch_set_for_legacy_patch",
                return_value=patch_set,
            ),
            patch(
                "apps.copilot.services.patch_apply.apply_accepted_patch_set",
                return_value=SimpleNamespace(
                    patch_set_id="pset-123",
                    document_id="99",
                    content="Contenido aplicado",
                    applied_version=4,
                    applied_patch_ids=["patch-123"],
                    stale_patch_set_ids=["pset-old"],
                    stale_patch_ids=["patch-old"],
                ),
            ),
        ):
            result = apply_copilot_patch(
                patch=patch_instance,
                document_version=3,
                review_comment="Aplicar",
            )

        patch_instance.save.assert_called_once_with(
            update_fields=["status", "review_comment", "updated_at"]
        )
        self.assertEqual(result.patch_id, "patch-123")
        self.assertEqual(result.document_id, "99")
        self.assertEqual(result.applied_version, 4)

    def test_apply_copilot_patch_bubbles_patch_set_conflicts(self):
        patch_instance = Mock(
            patch_id="patch-123",
            status="pending",
        )

        with (
            patch(
                "apps.copilot.services.patch_apply.ensure_patch_set_for_legacy_patch",
                return_value=Mock(),
            ),
            patch(
                "apps.copilot.services.patch_apply.apply_accepted_patch_set",
                side_effect=CopilotPatchConflictError("conflict"),
            ),
        ):
            with self.assertRaises(CopilotPatchConflictError):
                apply_copilot_patch(
                    patch=patch_instance,
                    document_version=3,
                    review_comment="Aplicar",
                )


class CopilotPatchSetServiceTests(SimpleTestCase):
    def test_resolve_patch_against_document_resolves_replace_span(self):
        resolved = _resolve_patch_against_document(
            preview={
                "patch_id": "patch-1",
                "patch_type": "replace_span",
                "operation_type": "replace_span",
                "order_index": 0,
                "anchor": {
                    "exactText": "Plan: hidratacion.",
                    "prefixText": "Motivo: dolor abdominal. ",
                    "suffixText": "",
                },
                "replacement_text": "Plan: hidratacion intensiva.",
                "content_preview": "Plan: hidratacion intensiva.",
            },
            document_content="Motivo: dolor abdominal. Plan: hidratacion.",
        )

        self.assertEqual(resolved["resolved_start"], 25)
        self.assertEqual(resolved["resolved_end"], 43)
        self.assertEqual(resolved["status"], "pending")

    def test_detect_internal_conflicts_marks_overlapping_patches(self):
        conflicted = _detect_internal_conflicts(
            [
                {
                    "patch_id": "patch-1",
                    "patch_type": "replace_span",
                    "resolved_start": 25,
                    "resolved_end": 43,
                    "order_index": 0,
                    "status": "pending",
                },
                {
                    "patch_id": "patch-2",
                    "patch_type": "insert_after",
                    "resolved_start": 25,
                    "resolved_end": 43,
                    "order_index": 1,
                    "status": "pending",
                },
            ]
        )

        self.assertEqual(conflicted[0]["status"], "conflicted")
        self.assertEqual(conflicted[1]["status"], "conflicted")
        self.assertEqual(conflicted[0]["conflict_reason"], "overlapping")

    def test_apply_patches_to_content_combines_accepted_changes(self):
        content = _apply_patches_to_content(
            "Motivo: dolor abdominal. Plan: hidratacion.",
            [
                {
                    "patch_id": "patch-1",
                    "patch_type": "replace_span",
                    "resolved_start": 25,
                    "resolved_end": 43,
                    "new_text": "Plan: hidratacion intensiva.",
                    "order_index": 0,
                }
            ],
        )

        self.assertEqual(
            content,
            "Motivo: dolor abdominal. Plan: hidratacion intensiva.",
        )

    def test_insert_after_does_not_duplicate_anchor(self):
        resolved = _resolve_patch_against_document(
            preview={
                "patch_id": "patch-1",
                "patch_type": "insert_after_span",
                "operation_type": "insert_after_span",
                "order_index": 0,
                "anchor": {
                    "exactText": "# TÍTULO",
                    "suffixText": " ## Sección",
                },
                "inserted_text": "\n6 de abril de 2026",
                "content_preview": "\n6 de abril de 2026",
            },
            document_content="# TÍTULO\n\n## Sección\nContenido.",
        )
        result = _apply_patches_to_content(
            "# TÍTULO\n\n## Sección\nContenido.",
            [resolved],
        )
        self.assertEqual(result, "# TÍTULO\n6 de abril de 2026\n\n## Sección\nContenido.")

    def test_insert_before_does_not_duplicate_anchor(self):
        resolved = _resolve_patch_against_document(
            preview={
                "patch_id": "patch-2",
                "patch_type": "insert_before",
                "operation_type": "insert_before",
                "order_index": 0,
                "anchor": {
                    "exactText": "# TÍTULO",
                    "prefixText": "",
                    "suffixText": " ## Sección",
                },
                "inserted_text": "Fecha: 06/04/2026\n",
                "content_preview": "Fecha: 06/04/2026\n",
            },
            document_content="# TÍTULO\n\n## Sección\nContenido.",
        )
        result = _apply_patches_to_content(
            "# TÍTULO\n\n## Sección\nContenido.",
            [resolved],
        )
        self.assertEqual(result, "Fecha: 06/04/2026\n# TÍTULO\n\n## Sección\nContenido.")

    def test_replace_span_rejects_repeated_prefix_in_replacement_text(self):
        with self.assertRaisesRegex(
            CopilotPatchSetConflictError,
            "replacement_repeats_prefix",
        ):
            _resolve_patch_against_document(
                preview={
                    "patch_id": "patch-3",
                    "patch_type": "replace_span",
                    "operation_type": "replace_span",
                    "order_index": 0,
                    "anchor": {
                        "exactText": "Hace cinco días inicia con tos",
                        "prefixText": "- Descripción cronológica del problema: ",
                    },
                    "replacement_text": (
                        "- Descripción cronológica del problema: "
                        "Hace cinco días inicia con cefalea severa"
                    ),
                },
                document_content=(
                    "- Descripción cronológica del problema: "
                    "Hace cinco días inicia con tos."
                ),
            )

    def test_replace_span_rejects_noop_replacement(self):
        with self.assertRaisesRegex(CopilotPatchSetConflictError, "patch_without_change"):
            _resolve_patch_against_document(
                preview={
                    "patch_id": "patch-4",
                    "patch_type": "replace_span",
                    "operation_type": "replace_span",
                    "order_index": 0,
                    "anchor": {"exactText": "Plan: hidratacion."},
                    "replacement_text": "Plan: hidratacion.",
                },
                document_content="Motivo: dolor abdominal. Plan: hidratacion.",
            )

    def test_content_hash_is_stable_for_same_text(self):
        self.assertEqual(content_hash("abc"), content_hash("abc"))
