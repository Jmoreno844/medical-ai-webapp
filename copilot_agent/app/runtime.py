from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import Connection
from psycopg.rows import dict_row

from app.backend_tools_client import CopilotBackendToolsClient
from app.config import Settings
from app.graph.state import CopilotState, materialize_state_snapshot
from app.graph.workflow import build_clinical_copilot_graph
from app.graph.nodes import (
    NODE_EXECUTE_TOOLS,
    NODE_FINALIZE_RUN,
    NODE_PLANNER_TURN,
    NODE_RECONCILE_TOOL_STATE,
)
from app.langsmith import finish_traced_operation, traced_operation
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


def _langsmith_create_run_inputs(request: RunCreateRequest) -> dict[str, Any]:
    return {
        "thread_id": request.thread_id,
        "tenant_id": request.tenant_id,
        "user_id": request.user_id,
        "encounter_id": request.encounter_id,
        "active_document_id": request.active_document_id,
        "selected_document_ids": request.selected_document_ids,
        "user_message_length": len(request.user_message),
        "workspace_document_count": len(request.workspace_index.documents),
        "workspace_open_document_count": len(request.workspace_index.open_document_ids),
    }


def _langsmith_resume_run_inputs(run_id: str, request) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "patch_set_id": request.patch_set_id,
        "review_result": request.review_result,
        "reviewer_id": request.reviewer_id,
        "comment_length": len(request.comment or ""),
    }


def _langsmith_run_outputs(stored_run: StoredRun, events_count: int) -> dict[str, Any]:
    patch_count = len((stored_run.patch_set_preview or {}).get("patches") or [])
    return {
        "run_id": stored_run.run_id,
        "thread_id": stored_run.thread_id,
        "status": stored_run.status,
        "intent": stored_run.intent,
        "requires_human_review": stored_run.requires_human_review,
        "active_patch_set_id": stored_run.active_patch_set_id,
        "patch_count": patch_count,
        "events_count": events_count,
        "final_response_length": len(stored_run.final_response or ""),
        "has_run_error": bool(stored_run.trace_metadata.get("run_error")),
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

    # ------------------------------------------------------------------ #
    # Streaming (async) run path                                           #
    # ------------------------------------------------------------------ #
    #
    # The legacy create_run() blocks for 15-30 s waiting for graph.invoke().
    # The streaming path below returns immediately from the HTTP endpoint
    # (bootstrap_run writes the initial run record + run_started event) and
    # runs the graph as a FastAPI BackgroundTask via run_graph_async().
    #
    # Django's existing SSE polling endpoint (stream_copilot_run) already
    # delivers events from the DB to the browser; it now gets live data
    # instead of a single burst at the end.
    #
    # Token-level streaming: AIMessageChunk tokens from NODE_PLANNER_TURN
    # (text responses without tool calls) are persisted as response_chunk
    # events.  The 1 s poll interval approximates a typewriter effect.
    # Google's disable_streaming="tool_calling" suppresses tokens only
    # during tool-calling turns, so plain conversational responses DO stream.

    @staticmethod
    def _build_initial_state(request: RunCreateRequest, settings: Settings) -> CopilotState:
        """Build the LangGraph input state from a create-run request.

        Extracted so both the sync path (create_run) and the async streaming
        path (run_graph_async) share identical initial state without duplication.
        """
        return {
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
            "max_iterations": settings.planner_max_iterations,
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

    def _persist_events_sync(
        self,
        run_id: str,
        thread_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        """Persist a batch of events in one DB round-trip (sync).

        Wrapped with asyncio.to_thread in run_graph_async so it can be
        awaited without blocking the event loop.
        """
        with self._connection() as conn:
            self._repository.append_events(
                conn,
                run_id=run_id,
                thread_id=thread_id,
                events=events,
            )

    def _update_run_sync(self, run: StoredRun) -> None:
        """Update an existing run record (sync).

        Wrapped with asyncio.to_thread in run_graph_async so it can be
        awaited without blocking the event loop.
        """
        with self._connection() as conn:
            self._repository.update_run(conn, run=run)

    def bootstrap_run(
        self,
        request: RunCreateRequest,
        *,
        run_id: str,
    ) -> tuple[StoredRun, list[RunEvent]]:
        """Create the initial run record (status='running') and persist run_started.

        Called synchronously before the graph starts so the HTTP endpoint can
        return run_id to Django in ~50 ms.  The graph itself runs separately
        in run_graph_async via FastAPI BackgroundTasks.
        """
        initial_run = StoredRun(
            run_id=run_id,
            thread_id=request.thread_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            encounter_id=request.encounter_id,
            status="running",
            intent=None,
            requires_human_review=False,
            active_patch_set_id=None,
            patch_set_preview=None,
            final_response=None,
            trace_metadata=request.trace_metadata,
        )
        with self._connection() as conn:
            self._repository.create_run(conn, run=initial_run)
            stored_events = self._repository.append_events(
                conn,
                run_id=run_id,
                thread_id=request.thread_id,
                events=[
                    {
                        "event": "run_started",
                        "payload": {"encounter_id": request.encounter_id},
                    }
                ],
            )
        return initial_run, [self._event_to_schema(e) for e in stored_events]

    async def run_graph_async(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
    ) -> None:
        """Run the LangGraph graph asynchronously, persisting events as each step completes.

        Intended to be registered as a FastAPI BackgroundTask after bootstrap_run().
        The existing SSE polling endpoint (backend stream_copilot_run) delivers
        events to the browser within ~1 s of each graph step completing.

        Event emission strategy:
        - NODE_PLANNER_TURN  → intent_classified + tool_called × N
        - NODE_EXECUTE_TOOLS → tool_result × N (uses payload-hash dedup to be safe
                               regardless of whether stream_mode="updates" returns
                               pre- or post-reducer values for _append_items fields)
        - NODE_RECONCILE     → retrieval_progress (when read_documents present)
        - messages mode      → response_chunk per token for planner text turns
        - terminal section   → patch events, review_required, run_completed/failed

        If token streaming doesn't fire (provider-dependent), the final response
        text is emitted as a single response_chunk in the terminal section.
        """
        state = self._build_initial_state(request, self._settings)

        tools_client = CopilotBackendToolsClient(
            settings=self._settings,
            run_id=run_id,
            thread_id=request.thread_id,
            encounter_id=request.encounter_id,
            user_id=request.user_id,
        )

        # Track emitted tool_calls by count.
        # tool_calls has no LangGraph reducer — NODE_PLANNER_TURN delta contains
        # the full accumulated list built by _append_state_items in nodes.py.
        emitted_tool_call_count = 0

        # Dedup tool_results by a short content key.
        # tool_results uses the _append_items reducer. stream_mode="updates" may
        # return either the pre- or post-reducer value depending on LangGraph version.
        # Hashing prevents duplicate tool_result events if the full accumulated list
        # is included in the delta.
        seen_tool_result_keys: set[str] = set()

        intent_emitted = False

        # True once any response_chunk was emitted during the messages phase.
        # The terminal section omits the full-text fallback if tokens already flowed.
        streamed_response_chunks = False

        try:
            async with AsyncPostgresSaver.from_conn_string(
                self._settings.database_url
            ) as checkpointer:
                graph = build_clinical_copilot_graph(
                    tools_client=tools_client,
                    planner=self._planner,
                    checkpointer=checkpointer,
                )
                async for mode, chunk in graph.astream(
                    state,
                    config={"configurable": {"thread_id": request.thread_id}},
                    stream_mode=["updates", "messages"],
                ):
                    # ── token-level streaming ──────────────────────────── #
                    if mode == "messages":
                        message_chunk, metadata = chunk
                        # Only forward plain-text tokens from the planner.
                        # tool_call_chunks are JSON fragments for tool arguments —
                        # never user-facing text.  Google's disable_streaming=
                        # "tool_calling" already suppresses tokens for tool turns,
                        # so this guard is belt-and-suspenders for other providers.
                        if (
                            isinstance(message_chunk, AIMessageChunk)
                            and metadata.get("langgraph_node") == NODE_PLANNER_TURN
                            and not message_chunk.tool_call_chunks
                        ):
                            token = message_chunk.content
                            if isinstance(token, str) and token:
                                streamed_response_chunks = True
                                await asyncio.to_thread(
                                    self._persist_events_sync,
                                    run_id,
                                    request.thread_id,
                                    [
                                        {
                                            "event": "response_chunk",
                                            "payload": {
                                                "content": token,
                                                "is_chunk": True,
                                            },
                                        }
                                    ],
                                )

                    # ── node-level step streaming ──────────────────────── #
                    elif mode == "updates":
                        step_events: list[dict[str, Any]] = []

                        for node_name, delta in chunk.items():
                            if node_name == NODE_PLANNER_TURN:
                                # Intent: emit once when first set by the planner.
                                new_intent = delta.get("intent")
                                if new_intent and not intent_emitted:
                                    intent_emitted = True
                                    step_events.append(
                                        {
                                            "event": "intent_classified",
                                            "payload": {"intent": new_intent},
                                        }
                                    )

                                # tool_calls: full accumulated list (no reducer).
                                # Emit only entries beyond the already-emitted count.
                                all_calls = delta.get("tool_calls") or []
                                new_calls = all_calls[emitted_tool_call_count:]
                                for tc in new_calls:
                                    step_events.append(
                                        {"event": "tool_called", "payload": tc}
                                    )
                                emitted_tool_call_count = len(all_calls)

                            elif node_name == NODE_EXECUTE_TOOLS:
                                # tool_results uses _append_items reducer.
                                # Dedup by short payload hash to handle both
                                # pre-reducer (new items only) and post-reducer
                                # (full accumulated list) delta shapes.
                                for tr in delta.get("tool_results") or []:
                                    if not isinstance(tr, dict):
                                        continue
                                    key = (
                                        f"{tr.get('tool_name')}:"
                                        f"{str(tr.get('payload', {}))[:120]}"
                                    )
                                    if key not in seen_tool_result_keys:
                                        seen_tool_result_keys.add(key)
                                        step_events.append(
                                            {"event": "tool_result", "payload": tr}
                                        )

                            elif node_name == NODE_RECONCILE_TOOL_STATE:
                                # Emit retrieval_progress after context consolidation
                                # so the doctor sees "reading document X" feedback
                                # in near real-time instead of only at run end.
                                if delta.get("retrieved_context") or delta.get(
                                    "read_documents"
                                ):
                                    read_docs = delta.get("read_documents") or []
                                    step_events.append(
                                        {
                                            "event": "retrieval_progress",
                                            "payload": {
                                                "retrieved_context": delta.get(
                                                    "retrieved_context"
                                                )
                                                or [],
                                                "read_documents": [
                                                    {
                                                        "document_id": d.get(
                                                            "document_id"
                                                        ),
                                                        "title": d.get("title"),
                                                        "read_mode": d.get("mode"),
                                                    }
                                                    for d in read_docs
                                                ],
                                                "read_spans": [],
                                                "search_query": delta.get(
                                                    "search_query"
                                                ),
                                                "search_queries": [],
                                                "search_results": [],
                                                "context_view": {},
                                                "encounter_context": {},
                                            },
                                        }
                                    )

                        if step_events:
                            await asyncio.to_thread(
                                self._persist_events_sync,
                                run_id,
                                request.thread_id,
                                step_events,
                            )

                # ── post-stream: finalize run ──────────────────────── #
                final_checkpoint = await graph.aget_state(
                    config={"configurable": {"thread_id": request.thread_id}}
                )

            # Materialize RESET_MARKER sentinels so _build_patch_set_preview
            # and _derive_status see clean lists, not the accumulated-with-sentinel
            # values kept in the LangGraph checkpoint.
            final_state = materialize_state_snapshot(dict(final_checkpoint.values))
            patch_set_preview = self._build_patch_set_preview(final_state)
            status = self._derive_status(
                final_state, patch_set_preview=patch_set_preview
            )
            final_response = (
                None
                if status == "waiting_review"
                else final_state.get("final_response") or final_state.get("run_error")
            )

            stored_run = StoredRun(
                run_id=run_id,
                thread_id=request.thread_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                encounter_id=request.encounter_id,
                status=status,
                intent=final_state.get("intent"),
                requires_human_review=final_state.get("requires_human_review", False),
                active_patch_set_id=(
                    patch_set_preview.get("patch_set_id") if patch_set_preview else None
                ),
                patch_set_preview=(
                    patch_set_preview if status == "waiting_review" else None
                ),
                final_response=final_response,
                trace_metadata={
                    **final_state.get("trace_metadata", {}),
                    **(
                        {"run_error": final_state.get("run_error")}
                        if final_state.get("run_error")
                        else {}
                    ),
                },
            )
            await asyncio.to_thread(self._update_run_sync, stored_run)

            # Terminal events: patch proposals, review gate, and run completion.
            # These are emitted after the run finishes because they require the
            # fully normalized patch_set_preview (built by _build_patch_set_preview)
            # which involves cross-referencing read_documents for the base_hash.
            terminal_events: list[dict[str, Any]] = []

            if self._has_valid_patch_set_preview(patch_set_preview):
                terminal_events.append(
                    {"event": "patch_set_proposed", "payload": {**patch_set_preview}}
                )
                for patch in patch_set_preview.get("patches") or []:
                    if isinstance(patch, dict):
                        terminal_events.append(
                            {
                                "event": "patch_proposed",
                                "payload": {
                                    **patch,
                                    "patch_set_id": patch_set_preview["patch_set_id"],
                                    "target_document_id": patch_set_preview[
                                        "target_document_id"
                                    ],
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
                and final_state.get("requires_human_review")
                and self._has_valid_patch_set_preview(patch_set_preview)
            ):
                patches = patch_set_preview.get("patches") or []
                terminal_events.append(
                    {
                        "event": "review_required",
                        "payload": {
                            "patch_set_id": patch_set_preview["patch_set_id"],
                            "patch_id": patches[0]["patch_id"] if patches else None,
                            "patch_ids": [
                                p["patch_id"]
                                for p in patches
                                if isinstance(p, dict) and p.get("patch_id")
                            ],
                            "target_document_id": patch_set_preview[
                                "target_document_id"
                            ],
                        },
                    }
                )

            if status == "completed" and final_response and not streamed_response_chunks:
                # Fallback: emit full text when no tokens were streamed (e.g. the
                # provider or LangGraph version doesn't surface tokens via
                # stream_mode="messages" for sync nodes running in thread pool).
                terminal_events.append(
                    {
                        "event": "response_chunk",
                        "payload": {"content": final_response},
                    }
                )

            if status == "completed":
                terminal_events.append(
                    {"event": "run_completed", "payload": {"status": status}}
                )
            elif status == "failed":
                terminal_events.append(
                    {
                        "event": "run_failed",
                        "payload": {
                            "error": final_state.get("run_error")
                            or final_state.get("final_response")
                            or "El run termino con un flujo inconsistente.",
                        },
                    }
                )

            if terminal_events:
                await asyncio.to_thread(
                    self._persist_events_sync,
                    run_id,
                    request.thread_id,
                    terminal_events,
                )

            logger.info(
                "Background graph run completed",
                extra={"run_id": run_id, "status": status},
            )

        except Exception as error:
            logger.exception("Background graph run failed for run %s", run_id)
            error_run = StoredRun(
                run_id=run_id,
                thread_id=request.thread_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                encounter_id=request.encounter_id,
                status="failed",
                intent=None,
                requires_human_review=False,
                active_patch_set_id=None,
                patch_set_preview=None,
                final_response=None,
                trace_metadata={
                    **request.trace_metadata,
                    "error_type": type(error).__name__,
                },
            )
            # Best-effort: persist failure state.  Ignore secondary errors so the
            # background task does not crash silently without any log output.
            try:
                await asyncio.to_thread(self._update_run_sync, error_run)
                await asyncio.to_thread(
                    self._persist_events_sync,
                    run_id,
                    request.thread_id,
                    [{"event": "run_failed", "payload": {"error": str(error)}}],
                )
            except Exception:
                logger.exception(
                    "Could not persist failure state for run %s", run_id
                )

    # ------------------------------------------------------------------ #
    # Legacy sync run path (used by tests and kept for backward compat)   #
    # ------------------------------------------------------------------ #

    def create_run(self, request: RunCreateRequest) -> tuple[StoredRun, list[RunEvent]]:
        run_id = str(uuid.uuid4())
        state = self._build_initial_state(request, self._settings)
        tools_client = CopilotBackendToolsClient(
            settings=self._settings,
            run_id=run_id,
            thread_id=request.thread_id,
            encounter_id=request.encounter_id,
            user_id=request.user_id,
        )

        with traced_operation(
            self._settings,
            name="copilot_agent.create_run",
            inputs=_langsmith_create_run_inputs(request),
            metadata={
                "thread_id": request.thread_id,
                "encounter_id": request.encounter_id,
            },
            tags=["create_run"],
        ) as langsmith_run:
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
                status = self._derive_status(
                    next_state,
                    patch_set_preview=patch_set_preview,
                )
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
                    patch_set_preview=(
                        patch_set_preview if status == "waiting_review" else None
                    ),
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

            finish_traced_operation(
                langsmith_run,
                outputs=_langsmith_run_outputs(stored_run, len(stored_events)),
            )
            return stored_run, [self._event_to_schema(event) for event in stored_events]

    def resume_run(
        self,
        run_id: str,
        request,
    ) -> tuple[StoredRun, list[RunEvent]]:
        with traced_operation(
            self._settings,
            name="copilot_agent.resume_run",
            inputs=_langsmith_resume_run_inputs(run_id, request),
            metadata={"run_id": run_id},
            tags=["resume_run"],
        ) as langsmith_run:
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

            finish_traced_operation(
                langsmith_run,
                outputs=_langsmith_run_outputs(updated_run, len(stored_events)),
                metadata={"review_result": request.review_result},
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
                    as_node=NODE_FINALIZE_RUN,
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
                    "replacement_text": patch_preview.get("replacement_text"),
                    "inserted_text": patch_preview.get("inserted_text"),
                    "old_text": patch_preview.get("old_text"),
                    "new_text": patch_preview.get("new_text"),
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
