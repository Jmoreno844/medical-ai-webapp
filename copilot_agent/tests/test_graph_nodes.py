from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.tools import build_graph_tools
from app.graph.workflow import build_clinical_copilot_graph
from app.llm.instructions import DOCUMENTS_ARE_DATA_RULE
from app.planner import (
    DraftedPatch,
    DraftedPatchPlan,
    LangChainCopilotPlanner,
    _filter_parallel_tool_calls,
)
from tests.fixtures_copilot import (
    FakeToolsClient,
    ScriptedPlanner,
    build_state,
    make_ai_response,
    make_ai_tool_call,
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
        return {
            "document_id": document_id,
            "encounter_id": "2",
            "title": "Nota clinica",
            "type": "note",
            "version": 7,
            "content_hash": "note-hash",
            "updated_at": "2026-04-02T10:00:00Z",
            "short_summary": "Nota clinica activa del encounter.",
            "excerpt": "**HISTORIA CLINICA**\nMotivo de consulta: Dolor de estomago.",
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
        return {
            "document_id": document_id,
            "title": "Nota clinica",
            "type": "note",
            "version": 7,
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


class _FakeStructuredRunnable:
    def __init__(self, *, result=None, error: Exception | None = None):
        self._result = result
        self._error = error
        self.invocation_kwargs: list[dict] = []

    def invoke(self, _messages, **kwargs):
        self.invocation_kwargs.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


class _FakePatchModel:
    def __init__(self, result):
        self.methods: list[str] = []
        self._result = result
        self.runnables: list[_FakeStructuredRunnable] = []

    def with_structured_output(self, _schema, *, method: str):
        self.methods.append(method)
        runnable = _FakeStructuredRunnable(result=self._result)
        self.runnables.append(runnable)
        return runnable


class _FakeInvalidPatchModel:
    def __init__(self, error: Exception):
        self.methods: list[str] = []
        self._error = error
        self.runnables: list[_FakeStructuredRunnable] = []

    def with_structured_output(self, _schema, *, method: str):
        self.methods.append(method)
        runnable = _FakeStructuredRunnable(error=self._error)
        self.runnables.append(runnable)
        return runnable


class _RecordingPlanner:
    def __init__(self, responses: list[AIMessage]):
        self._responses = list(responses)
        self.calls: list[list[object]] = []

    def invoke_model(self, **kwargs):
        self.calls.append(list(kwargs["messages"]))
        if not self._responses:
            raise RuntimeError("Recording planner ran out of responses")
        return self._responses.pop(0)

    def draft_patch_preview(self, **_kwargs):  # pragma: no cover - defensive
        raise AssertionError("draft_patch_preview should not be called in this test")


def test_langchain_planner_retries_once_before_raising():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    attempts = {"count": 0}

    def flaky_operation():
        attempts["count"] += 1
        raise RuntimeError("boom")

    try:
        planner._invoke_with_retry("planner tool calling", flaky_operation)
    except RuntimeError as error:
        assert "failed after 2 attempts" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected the planner retry helper to fail closed")

    assert attempts["count"] == 2


def test_provider_runtime_kwargs_disable_google_afc():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )

    kwargs = planner._provider_runtime_kwargs()

    assert kwargs["automatic_function_calling"].disable is True


def test_planner_system_instruction_enforces_sequential_tool_dependencies():
    instruction = LangChainCopilotPlanner._planner_system_instruction()

    assert "agente secuencial estricto" in instruction
    assert "varias herramientas de lectura o busqueda en paralelo" in instruction
    assert "read_* y propose_* en el mismo turno" in instruction
    assert "Solo puedes proponer una edicion por turno" in instruction
    assert DOCUMENTS_ARE_DATA_RULE in instruction


def test_patch_system_instruction_treats_clinical_context_as_data():
    instruction = LangChainCopilotPlanner._patch_system_instruction(
        requested_tool_name="propose_replace_span"
    )

    assert "La tool solicitada fue propose_replace_span." in instruction
    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert "Si el contexto es ambiguo o insuficiente, no inventes contenido clinico." in instruction


def test_parallel_read_tool_calls_are_preserved():
    message = make_ai_response("")
    message = message.model_copy(
        update={
            "tool_calls": [
                {"name": "read_document_summary", "args": {"document_id": "7"}, "id": "call-1", "type": "tool_call"},
                {"name": "read_document_span", "args": {"document_id": "8"}, "id": "call-2", "type": "tool_call"},
            ]
        }
    )

    filtered = _filter_parallel_tool_calls(message)

    assert [tool_call["name"] for tool_call in filtered.tool_calls] == [
        "read_document_summary",
        "read_document_span",
    ]


def test_mixed_read_and_propose_tool_calls_drop_proposals():
    message = make_ai_response("")
    message = message.model_copy(
        update={
            "tool_calls": [
                {"name": "read_document_span", "args": {"document_id": "7"}, "id": "call-1", "type": "tool_call"},
                {"name": "propose_replace_span", "args": {"target_document_id": "7"}, "id": "call-2", "type": "tool_call"},
                {"name": "read_document_summary", "args": {"document_id": "7"}, "id": "call-3", "type": "tool_call"},
            ]
        }
    )

    filtered = _filter_parallel_tool_calls(message)

    assert [tool_call["name"] for tool_call in filtered.tool_calls] == [
        "read_document_span",
        "read_document_summary",
    ]


def test_multiple_proposals_keep_only_first_call():
    message = make_ai_response("")
    message = message.model_copy(
        update={
            "tool_calls": [
                {"name": "propose_replace_span", "args": {"target_document_id": "7"}, "id": "call-1", "type": "tool_call"},
                {"name": "propose_insert_after_span", "args": {"target_document_id": "8"}, "id": "call-2", "type": "tool_call"},
                {"name": "propose_replace_span", "args": {"target_document_id": "9"}, "id": "call-3", "type": "tool_call"},
            ]
        }
    )

    filtered = _filter_parallel_tool_calls(message)

    assert [tool_call["name"] for tool_call in filtered.tool_calls] == [
        "propose_replace_span"
    ]
    assert filtered.tool_calls[0]["args"]["target_document_id"] == "7"


def test_patch_drafting_uses_only_json_schema():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._patch_model = _FakePatchModel(
        DraftedPatchPlan(
            rationale="Agregar fecha clinica.",
            document_preview_after="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.",
            patches=[
                DraftedPatch(
                    operation_type="insert_before",
                    anchor={
                        "exactText": "Paciente estable y con mejoria.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 29,
                    },
                    expected_hash="hash-demo",
                    before_preview="Paciente estable y con mejoria.",
                    after_preview="Fecha: 2 abril 2026\n\n",
                    document_preview_after="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.",
                    content_preview="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.",
                    rationale="Agregar fecha al inicio.",
                )
            ],
        )
    )

    result = planner.draft_patch_preview(
        state=build_state("agrega la fecha a la nota clinica"),
        target_document={"document_id": "99", "title": "Nota clinica", "type": "note", "version": 3},
        target_document_content="Paciente estable y con mejoria.",
        supporting_context=[],
        span_payload={
            "document_id": "99",
            "content_hash": "hash-demo",
            "start_offset": 0,
            "end_offset": 29,
        },
        requested_tool_name="propose_replace_span",
    )

    assert result.patches
    assert planner._patch_model.methods == ["json_schema"]
    assert all(
        runnable.invocation_kwargs[0]["automatic_function_calling"].disable is True
        for runnable in planner._patch_model.runnables
        if runnable.invocation_kwargs
    )


def test_patch_drafting_fails_closed_without_function_calling_fallback():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._patch_model = _FakeInvalidPatchModel(RuntimeError("Invalid json output"))

    try:
        planner.draft_patch_preview(
            state=build_state("agrega la fecha a la nota clinica"),
            target_document={
                "document_id": "99",
                "title": "Nota clinica",
                "type": "note",
                "version": 3,
            },
            target_document_content="Paciente estable y con mejoria.",
            supporting_context=[],
            span_payload={
                "document_id": "99",
                "content_hash": "hash-demo",
                "start_offset": 0,
                "end_offset": 29,
            },
            requested_tool_name="propose_replace_span",
        )
    except RuntimeError as error:
        assert "json_schema structured output" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected patch drafting to fail closed without fallback")

    assert planner._patch_model.methods == ["json_schema"]
    assert all(
        runnable.invocation_kwargs[0]["automatic_function_calling"].disable is True
        for runnable in planner._patch_model.runnables
        if runnable.invocation_kwargs
    )


def test_drafted_patch_schema_rejects_tool_names_and_defaults_rationale():
    valid_plan = DraftedPatchPlan.model_validate(
        {
            "patches": [
                {
                    "operation_type": "insert_after_span",
                    "content_preview": "Fecha: 24/07/2024\n",
                }
            ]
        }
    )

    assert valid_plan.patches[0].rationale == ""

    try:
        DraftedPatchPlan.model_validate(
            {
                "patches": [
                    {
                        "operation_type": "propose_insert_after_span",
                        "content_preview": "Fecha: 24/07/2024\n",
                    }
                ]
            }
        )
    except Exception as error:
        assert "insert_after_span" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected tool names to be rejected as patch operation_type")


def test_greeting_can_finish_without_tool_calls():
    planner = ScriptedPlanner(responses=[make_ai_response("Hola. Puedo ayudarte con el encounter actual.")])
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


def test_new_run_clears_stale_patch_review_state_before_planning():
    planner = ScriptedPlanner(responses=[make_ai_response("Hola. Puedo ayudarte con el encounter actual.")])
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )
    state = build_state("hola")
    state["patch_preview"] = {
        "patch_id": "stale-patch",
        "target_document_id": "99",
        "target_document_title": "Nota clinica",
        "target_selection_reason": "stale",
        "base_version": 3,
        "operation_type": "insert_after_span",
        "content_preview": "Contenido viejo",
    }
    state["patch_id"] = "stale-patch"
    state["requires_human_review"] = True
    state["final_response"] = "Respuesta vieja"
    state["review_result"] = "approve"

    next_state = graph.invoke(
        state,
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Hola. Puedo ayudarte con el encounter actual."
    assert next_state.get("patch_preview") is None
    assert next_state.get("patch_id") is None
    assert next_state.get("requires_human_review") is False


def test_same_thread_preserves_conversation_messages_across_runs():
    planner = _RecordingPlanner(
        [
            make_ai_response("Entendido, guardaré tu nombre."),
            make_ai_response("Ahora sí sé a qué te refieres."),
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
        checkpointer=InMemorySaver(),
    )
    thread_id = "copilot:encounter:12:doctor:7:chat:test"

    graph.invoke(
        build_state("Mi nombre es Juan Moreno"),
        config={"configurable": {"thread_id": thread_id}},
    )
    graph.invoke(
        build_state("hazlo"),
        config={"configurable": {"thread_id": thread_id}},
    )

    first_call_messages = planner.calls[0]
    second_call_messages = planner.calls[1]

    assert any(
        isinstance(message, HumanMessage)
        and message.content == "Mi nombre es Juan Moreno"
        for message in first_call_messages
    )
    assert any(
        isinstance(message, HumanMessage)
        and message.content == "Mi nombre es Juan Moreno"
        for message in second_call_messages
    )
    assert any(
        isinstance(message, AIMessage)
        and message.content == "Entendido, guardaré tu nombre."
        for message in second_call_messages
    )
    assert any(
        isinstance(message, HumanMessage) and message.content == "hazlo"
        for message in second_call_messages
    )


def test_same_thread_keeps_messages_but_resets_run_scoped_traces():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Necesito ver los documentos antes de responder.",
            ),
            make_ai_response("Primer turno completado."),
            make_ai_response("Segundo turno limpio."),
        ]
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
        checkpointer=InMemorySaver(),
    )
    thread_id = "copilot:encounter:12:doctor:7:chat:test"

    graph.invoke(
        build_state("lee los documentos abiertos"),
        config={"configurable": {"thread_id": thread_id}},
    )
    second_state = graph.invoke(
        build_state("hola de nuevo"),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert second_state["final_response"] == "Segundo turno limpio."
    assert second_state["tool_calls"] == []
    assert second_state["tool_results"] == []
    assert len(second_state["planner_decisions"]) == 1
    assert second_state["planner_decisions"][0]["action_type"] == "respond"


def test_summary_request_uses_tool_loop_with_minimal_reads():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Necesito ver los documentos abiertos primero.",
            ),
            make_ai_tool_call(
                tool_name="build_context_view",
                args={"active_document_id": "99", "include_document_ids": ["99", "12"]},
                tool_call_id="call-2",
                content="Necesito una vista de contexto sintetizada.",
            ),
            make_ai_tool_call(
                tool_name="search_documents",
                args={"query": "resumen encounter", "max_results": 1},
                tool_call_id="call-3",
                content="Buscaré una coincidencia puntual.",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "55", "max_chars": 500},
                tool_call_id="call-4",
                content="Leeré el span relevante antes de responder.",
            ),
            make_ai_response("Resumen listo del encounter demo."),
        ],
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
    assert len(next_state["read_documents"]) >= 1
    assert any(document["document_id"] == "55" for document in next_state["read_documents"])


def test_toolruntime_tools_bind_and_execute_inside_graph():
    tools = build_graph_tools(
        tools_client=FakeToolsClient(),
        planner=ScriptedPlanner(responses=[]),
    )
    tool_schemas = {
        tool.name: tool.tool_call_schema.model_json_schema()
        for tool in tools
    }
    assert all("runtime" not in schema.get("properties", {}) for schema in tool_schemas.values())
    assert "document_id" in tool_schemas["read_document_summary"].get("properties", {})
    assert "document_id" in tool_schemas["read_document_span"].get("properties", {})
    assert "target_document_id" in tool_schemas["propose_replace_span"].get(
        "properties",
        {},
    )
    assert tool_schemas["list_open_documents"].get("properties", {}) == {}
    propose_replace_tool = next(tool for tool in tools if tool.name == "propose_replace_span")
    propose_insert_tool = next(
        tool for tool in tools if tool.name == "propose_insert_after_span"
    )
    assert "Sequential precondition" in (propose_replace_tool.description or "")
    assert "Never call this in the same turn as read tools" in (
        propose_insert_tool.description or ""
    )

    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Primero listare los documentos abiertos.",
            ),
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-2",
                content="Ahora leeré el resumen del documento objetivo.",
            ),
            make_ai_response("Listo."),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("muestrame el resumen de la nota"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Listo."
    assert next_state["available_documents"]
    assert next_state["document_summaries"]["99"]["document_id"] == "99"


def test_edit_request_proposes_patch_after_tool_loop():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Primero necesito ver los documentos abiertos.",
            ),
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-2",
                content="Leeré el resumen del target.",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "99", "max_chars": 1200},
                tool_call_id="call-3",
                content="Leeré el span del target antes de editar.",
            ),
            make_ai_tool_call(
                tool_name="propose_insert_after_span",
                args={"target_document_id": "99"},
                tool_call_id="call-4",
                content="Ya puedo proponer un patch revisable.",
            ),
        ],
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
    assert next_state["patch_preview"]["content_preview"].endswith("Fecha: 2 abril 2026")


def test_tool_error_allows_self_correction_on_next_planner_turn():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="propose_insert_after_span",
                args={"target_document_id": "99"},
                tool_call_id="call-1",
                content="Intentaré proponer el patch ya.",
            ),
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-2",
                content="Corregiré leyendo el resumen primero.",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "99", "max_chars": 1200},
                tool_call_id="call-3",
                content="Ahora leeré el span correcto.",
            ),
            make_ai_tool_call(
                tool_name="propose_insert_after_span",
                args={"target_document_id": "99"},
                tool_call_id="call-4",
                content="Ahora sí puedo proponer el patch.",
            ),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("agrega la fecha al final de la nota clinica"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is True
    assert any(
        "Antes de proponer un patch debes leer el resumen del documento target"
        in result["summary"]
        for result in next_state["tool_results"]
    )
    assert next_state.get("last_tool_error") is None


def test_regression_edit_note_request_stays_in_waiting_review_path():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Necesito ver los documentos abiertos.",
            ),
            make_ai_tool_call(
                tool_name="build_context_view",
                args={
                    "active_document_id": "7",
                    "include_document_ids": ["3", "4", "7"],
                    "include_manual_context": True,
                },
                tool_call_id="call-2",
                content="Construiré una vista de contexto.",
            ),
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "7"},
                tool_call_id="call-3",
                content="Leeré el resumen del documento target.",
            ),
            make_ai_tool_call(
                tool_name="read_patch_history",
                args={"document_id": "7", "limit": 5},
                tool_call_id="call-4",
                content="Revisaré el historial de patches.",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "7", "max_chars": 1200},
                tool_call_id="call-5",
                content="Leeré el span del documento target.",
            ),
            make_ai_tool_call(
                tool_name="propose_insert_after_span",
                args={"target_document_id": "7"},
                tool_call_id="call-6",
                content="Ya tengo suficiente contexto para proponer el patch.",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Agregar fecha al inicio de la nota.",
            document_preview_after="Fecha: 2 abril 2026\n\n**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
            patches=[
                DraftedPatch(
                    operation_type="insert_before",
                    anchor={
                        "exactText": "**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 62,
                    },
                    expected_hash="note-hash",
                    before_preview="**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                    after_preview="Fecha: 2 abril 2026\n\n",
                    document_preview_after="Fecha: 2 abril 2026\n\n**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                    content_preview="Fecha: 2 abril 2026\n\n**HISTORIA CLINICA**\n\nMotivo de consulta: Dolor de estomago.",
                    rationale="Agregar fecha al inicio.",
                )
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=EncounterRegressionToolsClient(),
        planner=planner,
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
    assert "llm_target_document_id" in str(next_state["target_selection_reason"])
    assert next_state.get("run_error") is None


def test_draft_failure_fails_closed_instead_of_opening_review():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-1",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "99", "max_chars": 1200},
                tool_call_id="call-2",
            ),
            make_ai_tool_call(
                tool_name="propose_replace_span",
                args={"target_document_id": "99"},
                tool_call_id="call-3",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="LLM no pudo materializar el cambio con seguridad.",
            document_preview_after=None,
            patches=[],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state(
            "agrega la fecha al inicio de la nota clinica, y mi nombre con firma juan moreno al final"
        ),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is False
    assert next_state.get("patch_preview") is None
    assert next_state.get("run_error")
    assert "patch clinico" in next_state["run_error"]


def test_edit_request_can_finish_with_clarifying_question():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-1",
                content="Necesito leer el resumen primero.",
            ),
            make_ai_response("¿Cuál es tu nombre para agregarlo a la nota clínica?"),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("agrega mi nombre al final de la nota clinica"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is False
    assert next_state["final_response"] == "¿Cuál es tu nombre para agregarlo a la nota clínica?"
    assert next_state.get("run_error") is None


def test_multi_patch_plan_is_preserved_in_patch_set_preview():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-1",
            ),
            make_ai_tool_call(
                tool_name="read_document_span",
                args={"document_id": "99", "max_chars": 1200},
                tool_call_id="call-2",
            ),
            make_ai_tool_call(
                tool_name="propose_replace_span",
                args={"target_document_id": "99"},
                tool_call_id="call-3",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Agregar fecha al inicio y firma al final.",
            document_preview_after="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.\n\nFirma:\nJuan Moreno",
            patches=[
                DraftedPatch(
                    operation_type="insert_before",
                    anchor={
                        "exactText": "Paciente estable y con mejoria.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 29,
                    },
                    expected_hash="hash-demo",
                    before_preview="Paciente estable y con mejoria.",
                    after_preview="Fecha: 2 abril 2026\n\n",
                    document_preview_after="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.",
                    content_preview="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.",
                    rationale="Agregar fecha al inicio.",
                ),
                DraftedPatch(
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
                    after_preview="\n\nFirma:\nJuan Moreno",
                    document_preview_after="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.\n\nFirma:\nJuan Moreno",
                    content_preview="Fecha: 2 abril 2026\n\nPaciente estable y con mejoria.\n\nFirma:\nJuan Moreno",
                    rationale="Agregar firma al final.",
                ),
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("agrega la fecha al inicio de la nota clinica y firma juan moreno al final"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is True
    assert len(next_state["patch_set_preview"]["patches"]) == 2
    assert next_state["patch_set_preview"]["patches"][0]["operation_type"] == "insert_before"
    assert (
        next_state["patch_set_preview"]["patches"][1]["operation_type"]
        == "insert_after_span"
    )
    assert next_state["patch_preview"]["patch_id"] == next_state["patch_set_preview"]["patches"][0]["patch_id"]


def test_provider_failure_marks_run_as_failed():
    planner = ScriptedPlanner(model_error=RuntimeError("vertex unavailable"))
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("hola"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["run_error"] == "El planner del copiloto fallo al decidir el siguiente paso."
    assert next_state["requires_human_review"] is False
