from types import SimpleNamespace

import pytest

from app.graph.workflow import build_clinical_copilot_graph
from app.planner import HeuristicFallbackPlanner, PlannerDecision, VertexToolPlanner
from tests.fixtures_copilot import (
    FakeToolsClient,
    ScriptedPlanner,
    build_state,
    make_document,
)


class EncounterRegressionToolsClient(FakeToolsClient):
    def list_open_documents(self, _workspace_index):
        return {
            "documents": [
                make_document(
                    "3",
                    title="Contexto",
                    document_type="context",
                    ai_writable=False,
                    is_active=True,
                ),
                make_document(
                    "4",
                    title="Transcripcion",
                    document_type="transcription",
                    ai_writable=False,
                ),
                make_document(
                    "7",
                    title="Nota clinica",
                    document_type="note",
                ),
            ]
        }

    def read_document_summary(self, document_id: str):
        summaries = {
            "7": {
                "document_id": "7",
                "encounter_id": "2",
                "title": "Nota clinica",
                "type": "note",
                "version": 1,
                "content_hash": "note-hash",
                "updated_at": "2026-04-02T10:00:00Z",
                "short_summary": "Nota clinica activa del encounter.",
                "excerpt": "**HISTORIA CLINICA**\nMotivo de consulta: Dolor de estomago.",
            }
        }
        return summaries[document_id]

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
        spans = {
            "7": {
                "document_id": "7",
                "title": "Nota clinica",
                "type": "note",
                "version": 1,
                "content_hash": "note-hash",
                "content": "**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                "start_offset": 0,
                "end_offset": 62,
                "anchor": {
                    "exactText": "**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                    "prefixText": "",
                    "suffixText": "",
                    "startOffset": 0,
                    "endOffset": 62,
                },
            }
        }
        return spans[document_id]

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
                    "category": "plan",
                    "value": "El paciente tenia dolor de estomago.",
                    "source_document_id": "3",
                    "source_anchor": {
                        "exactText": "El paciente tenia dolor de estomago.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 35,
                    },
                    "confidence": 0.82,
                }
            ],
            "ambiguities": [],
            "source_document_ids": ["3", "4", "7"],
        }


def test_vertex_planner_accepts_null_tool_input_for_respond():
    planner = VertexToolPlanner(
        settings=SimpleNamespace(gcp_project_id="demo", gcp_region="us-central1", vertex_model="gemini-2.5-flash"),
        fallback=HeuristicFallbackPlanner(),
    )

    decision = planner._parse_decision(
        """
        {
          "action_type": "respond",
          "tool_name": null,
          "tool_input": null,
          "reasoning_summary": "simple greeting",
          "response_content": "Hola",
          "intent": "answer_question"
        }
        """,
        build_state("hola"),
    )

    assert decision.action_type == "respond"
    assert decision.tool_input == {}
    assert decision.response_content == "Hola"


def test_vertex_planner_normalizes_build_context_view_input_shape():
    planner = VertexToolPlanner(
        settings=SimpleNamespace(gcp_project_id="demo", gcp_region="us-central1", vertex_model="gemini-2.5-flash"),
        fallback=HeuristicFallbackPlanner(),
    )

    decision = planner._parse_decision(
        """
        {
          "action_type": "call_tool",
          "tool_name": "build_context_view",
          "tool_input": {
            "document_id": "7",
            "include_document_ids": "7",
            "unexpected": "drop-me"
          },
          "reasoning_summary": "Need context",
          "intent": "add_information_to_document"
        }
        """,
        build_state("agrega cualquier fecha a la nota clinica"),
    )

    assert decision.intent == "edit_document"
    assert decision.tool_input == {
        "active_document_id": "7",
        "include_document_ids": ["7"],
    }


def test_vertex_planner_rejects_respond_for_edit_requests():
    planner = VertexToolPlanner(
        settings=SimpleNamespace(gcp_project_id="demo", gcp_region="us-central1", vertex_model="gemini-2.5-flash"),
        fallback=HeuristicFallbackPlanner(),
    )

    with pytest.raises(ValueError, match="cannot finish an edit request with respond"):
        planner._parse_decision(
            """
            {
              "action_type": "respond",
              "tool_name": null,
              "tool_input": {},
              "reasoning_summary": "Done",
              "response_content": "Listo",
              "intent": "add_information_to_document"
            }
            """,
            build_state("agrega cualquier fecha a la nota clinica"),
        )


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


def test_regression_edit_note_request_stays_in_waiting_review_path():
    graph = build_clinical_copilot_graph(
        tools_client=EncounterRegressionToolsClient(),
        planner=HeuristicFallbackPlanner(),
    )
    state = build_state("agrega cualquier fecha a la nota clinica")
    state["encounter_id"] = "2"
    state["active_document_id"] = "3"
    state["workspace_index"]["encounter_id"] = "2"
    state["workspace_index"]["active_document_id"] = "3"
    state["workspace_index"]["open_document_ids"] = ["3", "4", "7"]

    next_state = graph.invoke(
        state,
        config={"configurable": {"thread_id": "copilot:encounter:2:doctor:1"}},
    )

    assert next_state["requires_human_review"] is True
    assert next_state["final_response"] is None
    assert next_state["patch_preview"]["target_document_id"] == "7"
    assert next_state["target_document_title"] == "Nota clinica"
    assert "title_family_match:clinical_note" in str(
        next_state["target_selection_reason"]
    )
    assert next_state.get("run_error") is None


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

    assert "No pude completar una accion del copiloto" in next_state["run_error"]


@pytest.mark.parametrize(
    ("user_message", "expected_tool"),
    [
        ("Hazme un resumen del encounter", "list_open_documents"),
        ("Que dice la nota clinica?", "list_open_documents"),
    ],
)
def test_heuristic_planner_requests_open_documents_when_workspace_is_empty(
    user_message: str,
    expected_tool: str,
):
    planner = HeuristicFallbackPlanner()

    decision = planner.plan_next_action(build_state(user_message))

    assert decision.action_type == "call_tool"
    assert decision.tool_name == expected_tool


def test_heuristic_planner_uses_context_view_before_searching():
    planner = HeuristicFallbackPlanner()
    state = build_state("Hazme un resumen del encounter")
    state["available_documents"] = [
        make_document("99", title="Nota clinica", document_type="note", is_active=True),
        make_document("12", title="Contexto del encuentro", document_type="context", ai_writable=False),
    ]

    decision = planner.plan_next_action(state)

    assert decision.action_type == "call_tool"
    assert decision.tool_name == "build_context_view"
    assert decision.tool_input["active_document_id"] == "99"


def test_heuristic_planner_answers_simple_greeting_without_documents():
    planner = HeuristicFallbackPlanner()

    decision = planner.plan_next_action(build_state("hola"))

    assert decision.action_type == "respond"
    assert "Hola." in str(decision.response_content)


def test_heuristic_planner_reads_search_hit_span_for_question():
    planner = HeuristicFallbackPlanner()
    state = build_state("Que medicamentos se mencionan?")
    state["available_documents"] = [
        make_document("99", title="Nota clinica", document_type="note", is_active=True),
    ]
    state["context_view"] = {"facts": [], "ambiguities": [], "source_document_ids": []}
    state["search_matches"] = [
        {
            "document_id": "55",
            "anchor": {
                "exactText": "Metformina 500 mg",
                "prefixText": "",
                "suffixText": "",
            },
        }
    ]

    decision = planner.plan_next_action(state)

    assert decision.action_type == "call_tool"
    assert decision.tool_name == "read_document_span"
    assert decision.tool_input["document_id"] == "55"
    assert decision.tool_input["exact_text"] == "Metformina 500 mg"


def test_heuristic_planner_prefers_note_title_over_active_context_for_edit():
    planner = HeuristicFallbackPlanner()
    state = build_state("a la nota clinica agregale la fecha de hoy 2 abril 2026")
    state["active_document_id"] = "12"
    state["available_documents"] = [
        make_document("12", title="Contexto del encuentro", document_type="context", ai_writable=False, is_active=True),
        make_document("99", title="Nota clinica", document_type="note"),
        make_document("77", title="Epicrisis de egreso", document_type="note"),
    ]
    state["context_view"] = {"facts": [], "ambiguities": [], "source_document_ids": ["12"]}

    decision = planner.plan_next_action(state)

    assert decision.action_type == "call_tool"
    assert decision.tool_name == "read_document_summary"
    assert decision.tool_input["document_id"] == "99"
    assert decision.target_document_hint == "nota"


def test_heuristic_planner_prefers_discharge_family_for_egreso_request():
    planner = HeuristicFallbackPlanner()
    state = build_state("haz el egreso con recomendaciones de salida")
    state["available_documents"] = [
        make_document("99", title="Nota clinica", document_type="note", is_active=True),
        make_document("77", title="Epicrisis de egreso", document_type="note"),
    ]
    state["context_view"] = {"facts": [], "ambiguities": [], "source_document_ids": ["99"]}

    decision = planner.plan_next_action(state)

    assert decision.action_type == "call_tool"
    assert decision.tool_name == "read_document_summary"
    assert decision.tool_input["document_id"] == "77"
    assert decision.target_document_hint == "egreso"


def test_heuristic_planner_returns_safe_response_when_no_editable_documents_exist():
    planner = HeuristicFallbackPlanner()
    state = build_state("corrige la nota")
    state["available_documents"] = [
        make_document("12", title="Contexto del encuentro", document_type="context", ai_writable=False, is_active=True),
        make_document("13", title="Transcripcion", document_type="transcription", ai_writable=False),
    ]
    state["context_view"] = {"facts": [], "ambiguities": [], "source_document_ids": ["12"]}

    decision = planner.plan_next_action(state)

    assert decision.action_type == "respond"
    assert "No encontre un documento editable" in str(decision.response_content)


def test_heuristic_planner_respects_iteration_limit():
    planner = HeuristicFallbackPlanner()
    state = build_state("Hazme un resumen del encounter")
    state["iteration_count"] = state["max_iterations"]

    decision = planner.plan_next_action(state)

    assert decision.action_type == "respond"
    assert decision.reasoning_summary == "iteration_limit_reached"


def test_heuristic_planner_respects_patch_budget():
    planner = HeuristicFallbackPlanner()
    state = build_state("agrega la fecha a la nota")
    state["available_documents"] = [
        make_document("99", title="Nota clinica", document_type="note", is_active=True),
    ]
    state["context_view"] = {"facts": [], "ambiguities": [], "source_document_ids": ["99"]}
    state["patch_operations_count"] = state["max_patch_operations"]

    decision = planner.plan_next_action(state)

    assert decision.action_type == "respond"
    assert decision.reasoning_summary == "patch_budget_reached"
