from app.graph.workflow import build_clinical_copilot_graph
from app.planner import DraftedPatch, PlannerDecision


class FakeToolsClient:
    def list_open_documents(self, _workspace_index):
        return {
            "documents": [
                {
                    "document_id": "99",
                    "title": "Nota clinica",
                    "type": "note",
                    "is_active": True,
                    "is_open": True,
                    "ai_writable": True,
                    "pinned_for_agent": False,
                    "version": 3,
                },
                {
                    "document_id": "12",
                    "title": "Contexto del encuentro",
                    "type": "context",
                    "is_active": False,
                    "is_open": True,
                    "ai_writable": False,
                    "pinned_for_agent": True,
                    "version": 1,
                },
                {
                    "document_id": "77",
                    "title": "Epicrisis de egreso",
                    "type": "note",
                    "is_active": False,
                    "is_open": True,
                    "ai_writable": True,
                    "pinned_for_agent": False,
                    "version": 2,
                },
            ]
        }

    def list_encounter_documents(self):
        return self.list_open_documents({})

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
            "short_summary": content[:120],
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

    def read_encounter_context(self):
        return {
            "encounter_id": "12",
            "encounter_name": "Encuentro demo",
            "occurred_at": "2026-04-02T10:00:00Z",
            "has_been_transcribed": True,
            "patient_id": None,
            "patient_summary": None,
        }

    def build_context_view(
        self,
        *,
        active_document_id: str | None = None,
        include_document_ids: list[str] | None = None,
        include_manual_context: bool = True,
    ):
        del active_document_id, include_document_ids, include_manual_context
        return {
            "facts": [
                {
                    "category": "diagnosis",
                    "value": "Paciente con dolor abdominal.",
                    "source_document_id": "12",
                    "source_anchor": {
                        "exactText": "Paciente con dolor abdominal.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 29,
                    },
                    "confidence": 0.8,
                }
            ],
            "ambiguities": [],
            "source_document_ids": ["12"],
        }


class ScriptedPlanner:
    def __init__(self, decisions, drafted_patch=None):
        self._decisions = list(decisions)
        self._drafted_patch = drafted_patch or DraftedPatch(
            operation_type="insert_after_span",
            anchor={
                "exactText": "Paciente estable y con mejoria.",
                "prefixText": "",
                "suffixText": "",
                "startOffset": 0,
                "endOffset": 29,
            },
            expected_hash="hash-demo",
            before_preview="Paciente estable y con mejoria.",
            after_preview="\n\nFecha: 2 abril 2026",
            document_preview_after="Paciente estable y con mejoria.\n\nFecha: 2 abril 2026",
            content_preview="Paciente estable y con mejoria.\n\nFecha: 2 abril 2026",
            rationale="Integrar fecha solicitada en la nota.",
        )

    def plan_next_action(self, _state):
        return self._decisions.pop(0)

    def draft_patch_preview(self, **_kwargs):
        return self._drafted_patch


def build_state(user_message="Hazme un resumen"):
    return {
        "tenant_id": "doctor:7",
        "user_id": "7",
        "encounter_id": "12",
        "active_document_id": "99",
        "thread_id": "copilot:encounter:12:doctor:7",
        "user_message": user_message,
        "workspace_index": {
            "encounter_id": "12",
            "workspace_version": "v1",
            "active_document_id": "99",
            "open_document_ids": ["99", "12", "77"],
            "documents": [],
        },
        "messages": [{"role": "user", "content": user_message}],
        "selected_document_ids": [],
        "available_documents": [],
        "context_view": None,
        "document_summaries": {},
        "read_spans": [],
        "retrieved_context": [],
        "read_documents": [],
        "encounter_context": None,
        "search_matches": [],
        "search_query": None,
        "patch_history": {},
        "tool_calls": [],
        "tool_results": [],
        "planner_decisions": [],
        "current_plan_step": "start",
        "pending_action": None,
        "pending_tool_result": None,
        "iteration_count": 0,
        "max_iterations": 6,
        "max_document_reads": 4,
        "patch_operations_count": 0,
        "max_patch_operations": 1,
        "requires_human_review": False,
        "trace_metadata": {},
    }


def test_greeting_can_finish_without_tool_calls():
    planner = ScriptedPlanner(
        [
            PlannerDecision(
                action_type="respond",
                intent="answer_question",
                response_content="Hola. Puedo ayudarte con el encounter actual.",
                reasoning_summary="simple_greeting",
            )
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("hola"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Hola. Puedo ayudarte con el encounter actual."
    assert next_state["tool_calls"] == []
    assert next_state["read_documents"] == []


def test_summary_request_uses_tool_loop_with_minimal_reads():
    planner = ScriptedPlanner(
        [
            PlannerDecision(
                action_type="call_tool",
                tool_name="list_open_documents",
                reasoning_summary="need documents",
                intent="answer_question",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="build_context_view",
                reasoning_summary="need context view",
                intent="answer_question",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="search_documents",
                tool_input={"query": "resumen encounter", "max_results": 1},
                reasoning_summary="need search match",
                intent="answer_question",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_span",
                tool_input={"document_id": "55", "max_chars": 500},
                reasoning_summary="need focused span",
                intent="answer_question",
            ),
            PlannerDecision(
                action_type="respond",
                response_content="Resumen listo del encounter demo.",
                reasoning_summary="enough context",
                intent="answer_question",
            ),
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("Hazme un resumen del encounter"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Resumen listo del encounter demo."
    assert [call["tool_name"] for call in next_state["tool_calls"]] == [
        "list_open_documents",
        "build_context_view",
        "search_documents",
        "read_document_span",
    ]
    assert len(next_state["read_documents"]) == 1
    assert next_state["read_documents"][0]["document_id"] == "55"


def test_edit_request_proposes_patch_after_tool_loop():
    planner = ScriptedPlanner(
        [
            PlannerDecision(
                action_type="call_tool",
                tool_name="list_open_documents",
                reasoning_summary="need docs",
                intent="edit_document",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="build_context_view",
                reasoning_summary="need context view",
                intent="edit_document",
                target_document_hint="nota",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_summary",
                tool_input={"document_id": "99"},
                reasoning_summary="need target summary",
                intent="edit_document",
                target_document_hint="nota",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_span",
                tool_input={"document_id": "99", "max_chars": 1200},
                reasoning_summary="need note span",
                intent="edit_document",
                target_document_hint="nota",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="propose_insert_after_span",
                tool_input={"target_document_id": "99"},
                reasoning_summary="ready to patch",
                intent="edit_document",
                target_document_hint="nota",
            ),
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("a la nota clinica agregale la fecha de hoy 2 abril 2026"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is True
    assert next_state["patch_preview"]["target_document_id"] == "99"
    assert next_state["target_document_title"] == "Nota clinica"
    assert next_state["patch_preview"]["document_preview_after"].endswith("Fecha: 2 abril 2026")


def test_egreso_request_can_target_discharge_family():
    planner = ScriptedPlanner(
        [
            PlannerDecision(
                action_type="call_tool",
                tool_name="list_open_documents",
                reasoning_summary="need docs",
                intent="edit_document",
                target_document_hint="egreso",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_summary",
                tool_input={"document_id": "77"},
                reasoning_summary="need egreso summary",
                intent="edit_document",
                target_document_hint="egreso",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="read_document_span",
                tool_input={"document_id": "77", "max_chars": 1200},
                reasoning_summary="need egreso span",
                intent="edit_document",
                target_document_hint="egreso",
            ),
            PlannerDecision(
                action_type="call_tool",
                tool_name="propose_replace_span",
                tool_input={"target_document_id": "77"},
                reasoning_summary="ready to patch egreso",
                intent="edit_document",
                target_document_hint="egreso",
            ),
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("haz el egreso con una nota de alta"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["patch_preview"]["target_document_id"] == "77"
    assert next_state["target_document_title"] == "Epicrisis de egreso"


def test_invalid_tool_finishes_with_safe_response():
    planner = ScriptedPlanner(
        [
            PlannerDecision(
                action_type="call_tool",
                tool_name="tool_que_no_existe",
                reasoning_summary="bad tool",
                intent="answer_question",
            )
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("Haz algo raro"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert "No pude completar una accion del copiloto" in next_state["final_response"]
