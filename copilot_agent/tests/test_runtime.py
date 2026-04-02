from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

from app.repository import StoredRun, StoredRunEvent
from app.runtime import CopilotRuntime
from app.schemas import RunResumeRequest


def test_resume_run_completes_waiting_review_run(monkeypatch):
    runtime = CopilotRuntime(settings=SimpleNamespace(database_url="postgresql://unused"))
    stored_run = StoredRun(
        run_id="run-123",
        thread_id="copilot:encounter:12:doctor:7",
        tenant_id="doctor:7",
        user_id="7",
        encounter_id="12",
        status="waiting_review",
        intent="edit_document",
        requires_human_review=True,
        patch_preview={
            "patch_id": "patch-123",
            "target_document_id": "99",
            "base_version": 3,
            "operation_type": "rewrite_document",
            "content_preview": "## Propuesta",
            "rationale": "Actualizar documento",
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
            patch_id="patch-123",
            review_result="approve",
            reviewer_id="7",
            comment="Aprobado",
            trace_metadata={
                "applied_patch_id": "patch-123",
                "applied_document_id": "99",
                "applied_content": "## Propuesta",
                "applied_version": 4,
            },
        ),
    )

    assert updated_run.status == "completed"
    assert updated_run.requires_human_review is False
    assert updated_run.patch_preview is None
    assert updated_run.trace_metadata["applied_version"] == 4
    assert [event.event for event in events] == [
        "patch_applied",
        "review_resolved",
        "response_chunk",
        "run_completed",
    ]
