from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row

from app.backend_tools_client import CopilotBackendToolsClient
from app.config import Settings
from app.graph.state import CopilotState
from app.graph.workflow import build_clinical_copilot_graph
from app.planner import build_planner
from app.repository import CopilotRunRepository, StoredRun
from app.schemas import (
    PatchSetPreview,
    RunCreateRequest,
    RunEvent,
    RunEventsResponse,
    RunStatusResponse,
)

logger = logging.getLogger(__name__)

DONE_STATUSES = {"completed", "failed", "waiting_review"}

PATCH_SET_REQUIRED_FIELDS = {
    "patch_set_id",
    "target_document_id",
    "target_document_title",
    "target_selection_reason",
    "base_version",
    "base_hash",
    "patches",
}


class CopilotRuntime:
    """Persist runs and thread state so Cloud Run restarts do not lose context."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._repository = CopilotRunRepository()
        self._planner = build_planner(settings)

    def setup(self) -> None:
        with self._connection() as conn:
            self._repository.setup(conn)
        with PostgresSaver.from_conn_string(self._settings.database_url) as checkpointer:
            checkpointer.setup()

    def create_run(self, request: RunCreateRequest) -> tuple[StoredRun, list[RunEvent]]:
        run_id = str(uuid.uuid4())
        state: CopilotState = {
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "encounter_id": request.encounter_id,
            "active_document_id": request.active_document_id,
            "thread_id": request.thread_id,
            "user_message": request.user_message,
            "workspace_index": request.workspace_index.model_dump(mode="python"),
            "messages": [HumanMessage(content=request.user_message)],
            "selected_document_ids": request.selected_document_ids,
            "available_documents": [],
            "context_view": None,
            "document_summaries": {},
            "document_reads": [],
            "read_spans": [],
            "retrieved_context": [],
            "read_documents": [],
            "encounter_context": None,
            "search_matches": [],
            "search_query": None,
            "search_results": [],
            "patch_history": {},
            "tool_calls": [],
            "tool_results": [],
            "planner_decisions": [],
            "current_plan_step": "start",
            "iteration_count": 0,
            "max_iterations": self._settings.planner_max_iterations,
            "max_document_reads": 4,
            "patch_operations_count": 0,
            "max_patch_operations": 1,
            "planner_retry_count": 0,
            "last_planner_error": None,
            "last_tool_error": None,
            "target_document_id": None,
            "target_document_title": None,
            "target_selection_reason": None,
            "base_version": None,
            "patch_set_preview": None,
            "patch_preview": None,
            "patch_id": None,
            "final_response": None,
            "requires_human_review": False,
            "review_result": None,
            "review_comment": None,
            "run_error": None,
            "trace_metadata": request.trace_metadata,
        }
        tools_client = CopilotBackendToolsClient(
            settings=self._settings,
            run_id=run_id,
            thread_id=request.thread_id,
            encounter_id=request.encounter_id,
            user_id=request.user_id,
        )

        try:
            with PostgresSaver.from_conn_string(self._settings.database_url) as checkpointer:
                graph = build_clinical_copilot_graph(
                    tools_client=tools_client,
                    planner=self._planner,
                    checkpointer=checkpointer,
                )
                # thread_id is the sidechat conversation identity. Reusing it as the
                # LangGraph checkpoint key gives the model persistent memory across
                # HTTP requests (prior messages stay visible). Per-run transient state
                # (reads, proposals, iteration counters) is cleared by call_model on
                # the first iteration (iteration_count == 0). See _reset_transient_run_state.
                next_state = graph.invoke(
                    state,
                    config={"configurable": {"thread_id": request.thread_id}},
                )
            patch_set_preview = self._build_patch_set_preview(next_state)
            # Edit runs must stop at waiting_review or fail closed; they cannot silently degrade to completed.
            status = self._derive_status(next_state, patch_set_preview=patch_set_preview)
            final_response = (
                None
                if status == "waiting_review"
                else next_state.get("final_response") or next_state.get("run_error")
            )
            stored_run = StoredRun(
                run_id=run_id,
                thread_id=request.thread_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                encounter_id=request.encounter_id,
                status=status,
                intent=next_state.get("intent"),
                requires_human_review=next_state.get("requires_human_review", False),
                active_patch_set_id=(
                    patch_set_preview.get("patch_set_id") if patch_set_preview else None
                ),
                patch_set_preview=patch_set_preview if status == "waiting_review" else None,
                final_response=final_response,
                trace_metadata={
                    **next_state.get("trace_metadata", {}),
                    **(
                        {"run_error": next_state.get("run_error")}
                        if next_state.get("run_error")
                        else {}
                    ),
                },
            )
            events = self._build_events(
                run_id=run_id,
                state=next_state,
                status=status,
                patch_set_preview=patch_set_preview,
            )
        except Exception as error:
            logger.exception("Copilot run failed before completion")
            stored_run = StoredRun(
                run_id=run_id,
                thread_id=request.thread_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                encounter_id=request.encounter_id,
                status="failed",
                intent=state.get("intent"),
                requires_human_review=False,
                active_patch_set_id=None,
                patch_set_preview=None,
                final_response=None,
                trace_metadata={
                    **request.trace_metadata,
                    "error_type": type(error).__name__,
                },
            )
            events = [
                {
                    "event": "run_started",
                    "payload": {"encounter_id": request.encounter_id},
                },
                {
                    "event": "run_failed",
                    "payload": {"error": str(error)},
                },
            ]

        with self._connection() as conn:
            self._repository.create_run(conn, run=stored_run)
            stored_events = self._repository.append_events(
                conn,
                run_id=stored_run.run_id,
                thread_id=stored_run.thread_id,
                events=events,
            )

        return stored_run, [self._event_to_schema(event) for event in stored_events]

    def resume_run(
        self,
        run_id: str,
        request,
    ) -> tuple[StoredRun, list[RunEvent]]:
        with self._connection() as conn:
            stored_run = self._repository.get_run(conn, run_id)

            if stored_run.status != "waiting_review":
                raise ValueError("Run is not waiting for review")
            if not stored_run.patch_set_preview:
                raise ValueError("Run does not have a pending patch set preview")
            if request.patch_set_id != (
                stored_run.active_patch_set_id
                or stored_run.patch_set_preview.get("patch_set_id")
            ):
                raise ValueError("Patch set id does not match the stored run")

            decision = request.review_result
            if decision == "approve":
                applied_patch_set_id = request.trace_metadata.get("applied_patch_set_id")
                applied_patch_id = request.trace_metadata.get("applied_patch_id")
                applied_document_id = request.trace_metadata.get("applied_document_id")
                applied_version = request.trace_metadata.get("applied_version")
                final_response = (
                    "El patch set del copiloto fue aprobado y aplicado al documento canonico."
                )
            else:
                applied_patch_set_id = None
                applied_patch_id = None
                applied_document_id = None
                applied_version = None
                final_response = (
                    "El patch set del copiloto fue rechazado. "
                    "No se aplicaron cambios al documento canonico."
                )

            updated_run = StoredRun(
                run_id=stored_run.run_id,
                thread_id=stored_run.thread_id,
                tenant_id=stored_run.tenant_id,
                user_id=stored_run.user_id,
                encounter_id=stored_run.encounter_id,
                status="completed",
                intent=stored_run.intent,
                requires_human_review=False,
                active_patch_set_id=None,
                patch_set_preview=None,
                final_response=final_response,
                trace_metadata={
                    **stored_run.trace_metadata,
                    **request.trace_metadata,
                    "review_result": decision,
                    "reviewer_id": request.reviewer_id,
                },
            )
            self._repository.update_run(conn, run=updated_run)
            stored_events = self._repository.append_events(
                conn,
                run_id=updated_run.run_id,
                thread_id=updated_run.thread_id,
                events=[
                    *(
                        [
                            {
                                "event": "patch_set_applied",
                                "payload": {
                                    "patch_set_id": applied_patch_set_id,
                                    "patch_id": applied_patch_id,
                                    "document_id": applied_document_id,
                                    "applied_version": applied_version,
                                },
                            }
                        ]
                        if decision == "approve"
                        and applied_patch_set_id
                        and applied_document_id
                        else []
                    ),
                    {
                        "event": "review_resolved",
                        "payload": {
                            "patch_set_id": request.patch_set_id,
                            "decision": decision,
                            "comment": request.comment,
                        },
                    },
                    {
                        "event": "response_chunk",
                        "payload": {"content": final_response},
                    },
                    {
                        "event": "run_completed",
                        "payload": {"status": "completed"},
                    },
                ],
            )

        self._append_review_resolution_to_thread(
            thread_id=updated_run.thread_id,
            encounter_id=updated_run.encounter_id,
            user_id=updated_run.user_id,
            run_id=updated_run.run_id,
            final_response=final_response,
        )

        return updated_run, [self._event_to_schema(event) for event in stored_events]

    def _append_review_resolution_to_thread(
        self,
        *,
        thread_id: str,
        encounter_id: str,
        user_id: str,
        run_id: str,
        final_response: str,
    ) -> None:
        # Review outcomes are persisted as run metadata/events, but future planner
        # turns reason over the thread checkpoint. Mirror the resolution back into
        # the conversation so the next user request does not keep treating the
        # previous edit flow as unresolved.
        try:
            tools_client = CopilotBackendToolsClient(
                settings=self._settings,
                run_id=run_id,
                thread_id=thread_id,
                encounter_id=encounter_id,
                user_id=user_id,
            )
            with PostgresSaver.from_conn_string(self._settings.database_url) as checkpointer:
                graph = build_clinical_copilot_graph(
                    tools_client=tools_client,
                    planner=self._planner,
                    checkpointer=checkpointer,
                )
                graph.update_state(
                    {"configurable": {"thread_id": thread_id}},
                    {
                        "messages": [
                            AIMessage(
                                content=(
                                    f"{final_response} "
                                    "Este flujo anterior ya quedo resuelto."
                                )
                            )
                        ]
                    },
                    as_node="finalize_response",
                )
        except Exception:
            logger.warning(
                "No pude reflejar la resolucion del review dentro del thread checkpoint",
                exc_info=True,
            )

    def get_run(self, run_id: str) -> StoredRun:
        with self._connection() as conn:
            return self._repository.get_run(conn, run_id)

    def list_run_events(
        self, run_id: str, *, after_sequence: int = 0
    ) -> RunEventsResponse:
        with self._connection() as conn:
            run = self._repository.get_run(conn, run_id)
            events = self._repository.list_events(
                conn,
                run_id,
                after_sequence=after_sequence,
            )

        return RunEventsResponse(
            events=[self._event_to_schema(event) for event in events],
            status=run.status,
            next_after_sequence=max([after_sequence, *[event.sequence for event in events]]),
            done=run.status in DONE_STATUSES,
        )

    @staticmethod
    def _has_valid_patch_set_preview(patch_set_preview: dict[str, Any] | None) -> bool:
        if not isinstance(patch_set_preview, dict):
            return False
        if not all(
            patch_set_preview.get(field_name) for field_name in PATCH_SET_REQUIRED_FIELDS
        ):
            return False
        patches = patch_set_preview.get("patches") or []
        if not isinstance(patches, list) or not patches:
            return False
        return True

    @staticmethod
    def _build_patch_set_preview(state: CopilotState) -> dict[str, Any] | None:
        patch_set_preview = state.get("patch_set_preview")
        if isinstance(patch_set_preview, dict):
            normalized_preview = dict(patch_set_preview)
            if not normalized_preview.get("base_hash"):
                target_document_id = str(normalized_preview.get("target_document_id") or "")
                for document in state.get("read_documents") or []:
                    if str(document.get("document_id")) == target_document_id:
                        normalized_preview["base_hash"] = document.get("content_hash")
                        break
                if not normalized_preview.get("base_hash"):
                    for span in state.get("read_spans") or []:
                        if str(span.get("document_id")) == target_document_id:
                            normalized_preview["base_hash"] = span.get("content_hash")
                            break
            if CopilotRuntime._has_valid_patch_set_preview(normalized_preview):
                return normalized_preview

        patch_preview = state.get("patch_preview")
        if not isinstance(patch_preview, dict):
            return None
        if not all(patch_preview.get(field_name) for field_name in {"patch_id", "target_document_id", "base_version"}):
            return None

        document_hash = None
        target_document_id = str(patch_preview["target_document_id"])
        for document in state.get("read_documents") or []:
            if str(document.get("document_id")) == target_document_id:
                document_hash = document.get("content_hash")
                break
        if not document_hash:
            for span in state.get("read_spans") or []:
                if str(span.get("document_id")) == target_document_id:
                    document_hash = span.get("content_hash")
                    break
        if not document_hash:
            document_hash = patch_preview.get("expected_hash")
        if not document_hash:
            return None

        # Legacy runs may still only populate patch_preview. Normalize that path
        # into a one-patch PatchSet so Django/frontend keep a single review model.
        patch_set_id = str(uuid.uuid4())
        return {
            "patch_set_id": patch_set_id,
            "target_document_id": target_document_id,
            "target_document_title": patch_preview.get("target_document_title")
            or state.get("target_document_title"),
            "target_selection_reason": patch_preview.get("target_selection_reason")
            or state.get("target_selection_reason"),
            "base_version": int(patch_preview.get("base_version") or 1),
            "base_hash": str(document_hash),
            "rationale": patch_preview.get("rationale"),
            "source_context_document_ids": patch_preview.get("source_context_document_ids") or [],
            "document_preview_after": patch_preview.get("document_preview_after")
            or patch_preview.get("content_preview"),
            "patches": [
                {
                    "patch_id": patch_preview["patch_id"],
                    "patch_type": patch_preview.get("operation_type"),
                    "operation_type": patch_preview.get("operation_type"),
                    "order_index": 0,
                    "anchor": patch_preview.get("anchor") or {},
                    "expected_hash": patch_preview.get("expected_hash"),
                    "old_text": patch_preview.get("before_preview"),
                    "new_text": patch_preview.get("after_preview"),
                    "before_preview": patch_preview.get("before_preview"),
                    "after_preview": patch_preview.get("after_preview"),
                    "document_preview_after": patch_preview.get("document_preview_after"),
                    "content_preview": patch_preview.get("content_preview"),
                    "rationale": patch_preview.get("rationale"),
                }
            ],
        }

    def _derive_status(
        self,
        state: CopilotState,
        *,
        patch_set_preview: dict[str, Any] | None = None,
    ) -> str:
        if self._has_valid_patch_set_preview(patch_set_preview) and state.get(
            "requires_human_review"
        ):
            return "waiting_review"
        if state.get("run_error"):
            return "failed"
        if state.get("final_response"):
            return "completed"
        return "completed"

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        conn = Connection.connect(
            self._settings.database_url,
            autocommit=True,
            row_factory=dict_row,
        )
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _build_events(
        *, run_id: str, state: CopilotState, status: str, patch_set_preview: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [
            {
                "event": "run_started",
                "payload": {"encounter_id": state["encounter_id"]},
            },
        ]
        if state.get("intent") is not None:
            events.append(
                {
                    "event": "intent_classified",
                    "payload": {"intent": state.get("intent")},
                }
            )
        events.append(
            {
                "event": "agent_decision",
                "payload": {
                    "intent": state.get("intent"),
                    "iteration_count": state.get("iteration_count"),
                    "last_decision": (state.get("planner_decisions") or [None])[-1],
                },
            }
        )

        for tool_call in state.get("tool_calls", []):
            events.append(
                {
                    "event": "tool_called",
                    "payload": tool_call,
                }
            )

        for tool_result in state.get("tool_results", []):
            events.append(
                {
                    "event": "tool_result",
                    "payload": tool_result,
                }
            )

        if state.get("selected_document_ids") or state.get("available_documents"):
            events.append(
                {
                    "event": "documents_selected",
                    "payload": {
                        "selected_document_ids": state["selected_document_ids"],
                        "available_document_ids": [
                            document["document_id"]
                            for document in state.get("available_documents", [])
                        ],
                    },
                }
            )

        encounter_context = state.get("encounter_context") or {}
        context_view = state.get("context_view") or {}
        search_results = state.get("search_results") or []
        if state.get("retrieved_context") or encounter_context or context_view or search_results:
            events.append(
                {
                    "event": "retrieval_progress",
                    "payload": {
                        "retrieved_context": state["retrieved_context"],
                        "read_documents": [
                            {
                                "document_id": document["document_id"],
                                "title": document["title"],
                                "read_mode": document["mode"],
                            }
                            for document in state.get("read_documents", [])
                        ],
                        "read_spans": [
                            {
                                "document_id": span["document_id"],
                                "title": span.get("title"),
                                "start_offset": span.get("start_offset"),
                                "end_offset": span.get("end_offset"),
                            }
                            for span in state.get("read_spans", [])
                        ],
                        "search_query": state.get("search_query"),
                        "search_queries": [
                            result.get("query")
                            for result in search_results
                            if result.get("query")
                        ],
                        "search_results": search_results,
                        "context_view": context_view,
                        "encounter_context": {
                            "encounter_id": encounter_context.get("encounter_id"),
                            "encounter_name": encounter_context.get("encounter_name"),
                            "has_been_transcribed": encounter_context.get(
                                "has_been_transcribed"
                            ),
                        },
                    },
                }
            )

        if CopilotRuntime._has_valid_patch_set_preview(patch_set_preview):
            events.append(
                {
                    "event": "patch_set_proposed",
                    "payload": {
                        **patch_set_preview,
                    },
                }
            )
            for patch in patch_set_preview.get("patches") or []:
                if not isinstance(patch, dict):
                    continue
                events.append(
                    {
                        "event": "patch_proposed",
                        "payload": {
                            **patch,
                            "patch_set_id": patch_set_preview["patch_set_id"],
                            "target_document_id": patch_set_preview["target_document_id"],
                            "target_document_title": patch_set_preview.get(
                                "target_document_title"
                            ),
                            "target_selection_reason": patch_set_preview.get(
                                "target_selection_reason"
                            ),
                            "base_version": patch_set_preview["base_version"],
                        },
                    }
                )
        if (
            status == "waiting_review"
            and state.get("requires_human_review")
            and CopilotRuntime._has_valid_patch_set_preview(patch_set_preview)
        ):
            events.append(
                {
                    "event": "review_required",
                    "payload": {
                        "patch_set_id": patch_set_preview["patch_set_id"],
                        "patch_id": patch_set_preview["patches"][0]["patch_id"],
                        "patch_ids": [
                            patch["patch_id"]
                            for patch in patch_set_preview.get("patches", [])
                            if isinstance(patch, dict) and patch.get("patch_id")
                        ],
                        "target_document_id": patch_set_preview["target_document_id"],
                    },
                }
            )
        if status == "completed" and state.get("final_response"):
            events.append(
                {
                    "event": "response_chunk",
                    "payload": {"content": state["final_response"]},
                }
            )

        if status == "completed":
            events.append({"event": "run_completed", "payload": {"status": status}})
        if status == "failed":
            events.append(
                {
                    "event": "run_failed",
                    "payload": {
                        "error": state.get("run_error")
                        or state.get("final_response")
                        or "El run termino con un flujo inconsistente de edicion.",
                    },
                }
            )
        return events

    @staticmethod
    def _event_to_schema(event) -> RunEvent:
        return RunEvent(
            sequence=event.sequence,
            event=event.event,
            run_id=event.run_id,
            thread_id=event.thread_id,
            created_at=event.created_at,
            payload=event.payload,
        )

    @staticmethod
    def to_status_response(stored_run: StoredRun) -> RunStatusResponse:
        patch_set_preview = stored_run.patch_set_preview
        return RunStatusResponse(
            run_id=stored_run.run_id,
            thread_id=stored_run.thread_id,
            status=stored_run.status,
            intent=stored_run.intent,
            requires_human_review=stored_run.requires_human_review,
            active_patch_set_id=stored_run.active_patch_set_id,
            patch_set_preview=PatchSetPreview(**patch_set_preview)
            if patch_set_preview
            else None,
            final_response=stored_run.final_response,
            applied_patch_set_id=stored_run.trace_metadata.get("applied_patch_set_id"),
            applied_patch_id=stored_run.trace_metadata.get("applied_patch_id"),
            applied_document_id=stored_run.trace_metadata.get("applied_document_id"),
            applied_content=stored_run.trace_metadata.get("applied_content"),
            applied_version=stored_run.trace_metadata.get("applied_version"),
            trace_metadata=stored_run.trace_metadata,
        )
