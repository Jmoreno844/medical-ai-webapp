from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.planner import DraftedPatch, DraftedPatchPlan


class FakeToolsClient:
    def list_open_documents(self, _workspace_index):
        return {
            "documents": [
                make_document(
                    "99",
                    title="Nota clinica",
                    document_type="note",
                    is_active=True,
                    version=3,
                ),
                make_document(
                    "12",
                    title="Contexto del encuentro",
                    document_type="context",
                    ai_writable=False,
                    version=1,
                ),
                make_document(
                    "77",
                    title="Epicrisis de egreso",
                    document_type="note",
                    version=2,
                ),
            ]
        }

    def list_encounter_documents(self):
        return self.list_open_documents({})

    def read_document(self, document_id: str, *, mode: str = "excerpt"):
        summary_payload = self.read_document_summary(document_id)
        if mode == "summary":
            return {
                **summary_payload,
                "mode": "summary",
                "content": None,
            }

        content = {
            "99": "Paciente estable y con mejoria.",
            "12": "Paciente con dolor abdominal.",
            "77": "Paciente egresa estable.",
            "55": "Coincidencia de busqueda.",
        }[document_id]
        return {
            "document_id": document_id,
            "encounter_id": "12",
            "title": summary_payload["title"],
            "type": summary_payload["type"],
            "version": 3,
            "content_hash": "hash-demo",
            "updated_at": "2026-04-02T10:00:00Z",
            "mode": mode,
            "content": content if mode == "full" else None,
            "excerpt": content,
        }

    def read_document_summary(self, document_id: str):
        title = {
            "99": "Nota clinica",
            "12": "Contexto del encuentro",
            "77": "Epicrisis de egreso",
            "55": "Nota relacionada",
        }[document_id]
        document_type = {
            "99": "note",
            "12": "context",
            "77": "note",
            "55": "note",
        }[document_id]
        content = {
            "99": "Paciente estable y con mejoria.",
            "12": "Paciente con dolor abdominal.",
            "77": "Paciente egresa estable.",
            "55": "Coincidencia de busqueda.",
        }[document_id]
        return {
            "document_id": document_id,
            "encounter_id": "12",
            "title": title,
            "type": document_type,
            "version": 3,
            "content_hash": "hash-demo",
            "updated_at": "2026-04-02T10:00:00Z",
            "excerpt": content,
        }

    def read_document_span(
        self,
        document_id: str,
        *,
        exact_text: str | None = None,
        prefix_text: str | None = None,
        suffix_text: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        max_chars: int = 600,
    ):
        del exact_text, prefix_text, suffix_text, start_offset, end_offset, max_chars
        title = {
            "99": "Nota clinica",
            "12": "Contexto del encuentro",
            "77": "Epicrisis de egreso",
            "55": "Nota relacionada",
        }[document_id]
        document_type = {
            "99": "note",
            "12": "context",
            "77": "note",
            "55": "note",
        }[document_id]
        content = {
            "99": "Paciente estable y con mejoria.",
            "12": "Paciente con dolor abdominal.",
            "77": "Paciente egresa estable.",
            "55": "Coincidencia de busqueda.",
        }[document_id]
        return {
            "document_id": document_id,
            "title": title,
            "type": document_type,
            "version": 3,
            "content_hash": "hash-demo",
            "content": content,
            "start_offset": 0,
            "end_offset": len(content),
            "anchor": {
                "exactText": content,
                "prefixText": "",
                "suffixText": "",
                "startOffset": 0,
                "endOffset": len(content),
            },
        }

    def search_documents(self, *, query: str, max_results: int = 3, allowed_document_types=None):
        del allowed_document_types
        return {
            "query": query,
            "matches": [
                {
                    "document_id": "55",
                    "title": "Nota relacionada",
                    "type": "note",
                    "updated_at": "2026-04-02T10:00:00Z",
                    "snippet": "Coincidencia de busqueda",
                    "score": 0.81,
                    "anchor": {
                        "exactText": "Coincidencia de busqueda.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 24,
                    },
                }
            ][:max_results],
        }

    def read_patch_history(self, document_id: str, *, limit: int = 5):
        del limit
        return {"document_id": document_id, "patches": []}


class ScriptedPlanner:
    def __init__(
        self,
        *,
        responses: list[AIMessage] | None = None,
        drafted_patch: DraftedPatchPlan | None = None,
        model_error: Exception | None = None,
        draft_error: Exception | None = None,
    ):
        self._responses = list(responses or [])
        self._drafted_patch = drafted_patch or default_drafted_patch_plan()
        self._model_error = model_error
        self._draft_error = draft_error

    def invoke_model(self, **_kwargs):
        if self._model_error is not None:
            raise self._model_error
        if not self._responses:
            raise RuntimeError("Scripted planner ran out of AI messages")
        return self._responses.pop(0)

    def draft_patch_preview(self, **_kwargs):
        if self._draft_error is not None:
            raise self._draft_error
        return self._drafted_patch


def make_ai_tool_call(
    *,
    tool_name: str,
    args: dict | None = None,
    tool_call_id: str,
    content: str = "",
) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[
            {
                "name": tool_name,
                "args": args or {},
                "id": tool_call_id,
                "type": "tool_call",
            }
        ],
    )


def make_ai_response(content: str) -> AIMessage:
    return AIMessage(content=content)


def default_drafted_patch() -> DraftedPatch:
    return DraftedPatch(
        operation_type="insert_after_span",
        anchor={
            "exactText": "Paciente estable y con mejoria.",
            "prefixText": "",
            "suffixText": "",
            "startOffset": 0,
            "endOffset": 29,
        },
        expected_hash="hash-demo",
        inserted_text="\n\nFecha: 2 abril 2026",
        rationale="Integrar fecha solicitada en la nota.",
    )


def default_drafted_patch_plan() -> DraftedPatchPlan:
    patch = default_drafted_patch()
    return DraftedPatchPlan(
        rationale=patch.rationale,
        document_preview_after="Paciente estable y con mejoria.\n\nFecha: 2 abril 2026",
        patches=[patch],
    )


def build_state(user_message: str = "Hazme un resumen") -> dict:
    return {
        "tenant_id": "doctor:7",
        "user_id": "7",
        "encounter_id": "12",
        "active_document_id": "99",
        "thread_id": "copilot:encounter:12:doctor:7:chat:test",
        "user_message": user_message,
        "workspace_index": {
            "encounter_id": "12",
            "workspace_version": "v1",
            "active_document_id": "99",
            "open_document_ids": ["99", "12", "77"],
            "documents": [],
        },
        "messages": [HumanMessage(content=user_message)],
        "selected_document_ids": [],
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
        "max_iterations": 6,
        "max_document_reads": 4,
        "patch_operations_count": 0,
        "max_patch_operations": 1,
        "planner_retry_count": 0,
        "last_planner_error": None,
        "last_tool_error": None,
        "requires_human_review": False,
        "trace_metadata": {},
    }


def make_document(
    document_id: str,
    *,
    title: str,
    document_type: str,
    ai_writable: bool = True,
    is_active: bool = False,
    version: int = 1,
) -> dict:
    return {
        "document_id": document_id,
        "title": title,
        "type": document_type,
        "is_active": is_active,
        "is_open": True,
        "ai_writable": ai_writable,
        "pinned_for_agent": False,
        "version": version,
    }
