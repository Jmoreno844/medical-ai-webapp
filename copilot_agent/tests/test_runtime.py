from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

from app.repository import StoredRun, StoredRunEvent
from app.runtime import CopilotRuntime
from app.schemas import RunCreateRequest, RunResumeRequest, WorkspaceIndexPayload


def test_resume_run_completes_waiting_review_run(monkeypatch):
    runtime = CopilotRuntime(settings=SimpleNamespace(database_url="postgresql://unused"))
    stored_run = StoredRun(
        run_id="run-123",
        thread_id="copilot:encounter:12:doctor:7:chat:test",
        tenant_id="doctor:7",
        user_id="7",
        encounter_id="12",
        status="waiting_review",
        intent="edit_document",
        requires_human_review=True,
        active_patch_set_id="pset-123",
        patch_set_preview={
            "patch_set_id": "pset-123",
            "target_document_id": "99",
            "target_document_title": "Nota clínica",
            "target_selection_reason": "title_family_match:clinical_note",
            "base_version": 3,
            "base_hash": "hash-123",
            "rationale": "Actualizar documento",
            "patches": [
                {
                    "patch_id": "patch-123",
                    "patch_type": "replace_span",
                    "operation_type": "rewrite_document",
                    "content_preview": "## Propuesta",
                }
            ],
        },
        final_response=None,
        trace_metadata={},
    )

    monkeypatch.setattr(runtime, "_connection", lambda: nullcontext(object()))
    monkeypatch.setattr(
        runtime._repository,
        "get_run",
        lambda conn, run_id: stored_run,
    )
    monkeypatch.setattr(
        runtime._repository,
        "update_run",
        lambda conn, run: None,
    )
    monkeypatch.setattr(
        runtime._repository,
        "append_events",
        lambda conn, run_id, thread_id, events: [
            StoredRunEvent(
                sequence=index,
                event=event["event"],
                run_id=run_id,
                thread_id=thread_id,
                created_at=datetime.now(timezone.utc),
                payload=event["payload"],
            )
            for index, event in enumerate(events, start=1)
        ],
    )

    updated_run, events = runtime.resume_run(
        "run-123",
        RunResumeRequest(
            patch_set_id="pset-123",
            review_result="approve",
            reviewer_id="7",
            comment="Aprobado",
            trace_metadata={
                "applied_patch_set_id": "pset-123",
                "applied_patch_id": "patch-123",
                "applied_document_id": "99",
                "applied_content": "## Propuesta",
                "applied_version": 4,
            },
        ),
    )

    assert updated_run.status == "completed"
    assert updated_run.requires_human_review is False
    assert updated_run.patch_set_preview is None
    assert updated_run.trace_metadata["applied_version"] == 4
    assert [event.event for event in events] == [
        "patch_set_applied",
        "review_resolved",
        "response_chunk",
        "run_completed",
    ]


def test_runtime_marks_inconsistent_edit_flow_as_failed():
    runtime = CopilotRuntime(settings=SimpleNamespace(database_url="postgresql://unused"))
    inconsistent_state = {
        "intent": "edit_document",
        "requires_human_review": False,
        "patch_preview": None,
        "final_response": "Contexto sintetizado: ...",
        "run_error": "La solicitud de edicion no produjo un patch revisable y el run se cancelo de forma segura.",
    }

    status = runtime._derive_status(inconsistent_state)
    events = runtime._build_events(
        run_id="run-123",
        state={
            "encounter_id": "12",
            "selected_document_ids": [],
            "available_documents": [],
            "retrieved_context": [],
            "tool_calls": [],
            "tool_results": [],
            "intent": "edit_document",
            "iteration_count": 1,
            **inconsistent_state,
        },
        status=status,
        patch_set_preview=None,
    )

    assert status == "failed"
    assert [event["event"] for event in events][-1] == "run_failed"
    assert all(event["event"] != "run_completed" for event in events)


def test_runtime_completes_edit_run_when_it_returns_clarifying_response():
    runtime = CopilotRuntime(settings=SimpleNamespace(database_url="postgresql://unused"))
    clarifying_state = {
        "intent": "edit_document",
        "requires_human_review": False,
        "patch_preview": None,
        "patch_set_preview": None,
        "final_response": "¿Cuál es tu nombre para agregarlo a la nota clínica?",
        "run_error": None,
    }

    status = runtime._derive_status(clarifying_state)
    events = runtime._build_events(
        run_id="run-123",
        state={
            "encounter_id": "12",
            "selected_document_ids": [],
            "available_documents": [],
            "retrieved_context": [],
            "tool_calls": [],
            "tool_results": [],
            "intent": "edit_document",
            "iteration_count": 2,
            **clarifying_state,
        },
        status=status,
        patch_set_preview=None,
    )

    assert status == "completed"
    assert [event["event"] for event in events][-1] == "run_completed"
    assert all(event["event"] != "run_failed" for event in events)


def test_runtime_omits_intent_classified_event_when_intent_is_unknown():
    runtime = CopilotRuntime(settings=SimpleNamespace(database_url="postgresql://unused"))

    events = runtime._build_events(
        run_id="run-123",
        state={
            "encounter_id": "12",
            "selected_document_ids": [],
            "available_documents": [],
            "retrieved_context": [],
            "tool_calls": [],
            "tool_results": [],
            "intent": None,
            "iteration_count": 1,
            "planner_decisions": [],
            "requires_human_review": False,
            "final_response": "Hola.",
            "run_error": None,
        },
        status="completed",
        patch_set_preview=None,
    )

    event_names = [event["event"] for event in events]
    assert "intent_classified" not in event_names
    assert "agent_decision" in event_names


def test_create_run_uses_public_thread_id_for_checkpoint(monkeypatch):
    runtime = CopilotRuntime(
        settings=SimpleNamespace(
            database_url="postgresql://unused",
            planner_max_iterations=6,
            backend_internal_base_url="http://backend.test",
            copilot_service_shared_jwt="secret",
        )
    )

    class _FakeGraph:
        def __init__(self):
            self.config = None

        def invoke(self, state, config):
            self.config = config
            return {
                **state,
                "intent": "answer_question",
                "iteration_count": 1,
                "tool_calls": [],
                "tool_results": [],
                "planner_decisions": [],
                "selected_document_ids": state["selected_document_ids"],
                "available_documents": [],
                "retrieved_context": [],
                "final_response": "Hola.",
                "run_error": None,
                "requires_human_review": False,
            }

    fake_graph = _FakeGraph()

    class _FakeCheckpointer:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(runtime, "_connection", lambda: nullcontext(object()))
    monkeypatch.setattr(runtime._repository, "create_run", lambda conn, run: None)
    monkeypatch.setattr(
        runtime._repository,
        "append_events",
        lambda conn, run_id, thread_id, events: [
            StoredRunEvent(
                sequence=index,
                event=event["event"],
                run_id=run_id,
                thread_id=thread_id,
                created_at=datetime.now(timezone.utc),
                payload=event["payload"],
            )
            for index, event in enumerate(events, start=1)
        ],
    )
    monkeypatch.setattr("app.runtime.PostgresSaver.from_conn_string", lambda _dsn: _FakeCheckpointer())
    monkeypatch.setattr("app.runtime.build_clinical_copilot_graph", lambda **_kwargs: fake_graph)

    stored_run, _events = runtime.create_run(
        RunCreateRequest(
            tenant_id="doctor:7",
            user_id="7",
            encounter_id="12",
            thread_id="copilot:encounter:12:doctor:7:chat:test",
            user_message="hola",
            active_document_id="99",
            selected_document_ids=["99"],
            workspace_index=WorkspaceIndexPayload(
                encounter_id="12",
                workspace_version="v1",
                active_document_id="99",
                open_document_ids=["99"],
                documents=[],
            ),
            trace_metadata={},
        )
    )

    assert stored_run.thread_id == "copilot:encounter:12:doctor:7:chat:test"
    checkpoint_thread_id = fake_graph.config["configurable"]["thread_id"]
    assert checkpoint_thread_id == "copilot:encounter:12:doctor:7:chat:test"
