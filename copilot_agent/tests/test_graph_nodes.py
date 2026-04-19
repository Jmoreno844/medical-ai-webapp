from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.tools import build_graph_tools
from app.graph.tools import draft_patch_set_from_state
from app.graph.tools import _is_valid_patch_preview as tool_patch_preview_is_valid
from app.graph.tools import _normalize_factual_replacements
from app.graph.tools import _validate_drafted_plan_against_clinical_plan
from app.graph.workflow import build_clinical_copilot_graph
from app.graph.state import materialize_state_snapshot, reset_dict_state, reset_list_state
from app.llm.instructions import DOCUMENTS_ARE_DATA_RULE
from app.llm.providers import LlmProviderSpec
from app.planner import (
    DraftedPatch,
    DraftedPatchPlan,
    DraftedSectionOutcome,
    LangChainCopilotPlanner,
    _filter_parallel_tool_calls,
)
from app.graph.nodes import (
    NODE_DRAFT_PATCH_FROM_PLAN,
    _derive_read_documents,
    _is_valid_patch_preview as node_patch_preview_is_valid,
    _read_document_view,
    _reset_transient_run_state,
    make_draft_patch_from_plan_node,
    route_after_tool_execution,
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
        self.configs: list[dict] = []
        self.invocation_kwargs: list[dict] = []

    def with_config(self, config=None, **kwargs):
        self.configs.append({**(config or {}), **kwargs})
        return self

    def invoke(self, _messages, **kwargs):
        self.invocation_kwargs.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


class _FakePlannerModel:
    def __init__(self, result):
        self._result = result
        self.bound_tools = None
        self.runnables: list[_FakeStructuredRunnable] = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        runnable = _FakeStructuredRunnable(result=self._result)
        self.runnables.append(runnable)
        return runnable


class _FakePatchModel:
    def __init__(self, result):
        self.methods: list[str] = []
        self._result = result
        self.runnables: list[_FakeStructuredRunnable] = []

    def with_structured_output(self, _schema, *, method: str | None = None):
        self.methods.append(method or "default")
        runnable = _FakeStructuredRunnable(result=self._result)
        self.runnables.append(runnable)
        return runnable


class _FakeInvalidPatchModel:
    def __init__(self, error: Exception):
        self.methods: list[str] = []
        self._error = error
        self.runnables: list[_FakeStructuredRunnable] = []

    def with_structured_output(self, _schema, *, method: str | None = None):
        self.methods.append(method or "default")
        runnable = _FakeStructuredRunnable(error=self._error)
        self.runnables.append(runnable)
        return runnable


ChatGoogleGenerativeAIFake = type("ChatGoogleGenerativeAI", (), {})
ChatGoogleGenerativeAIPatchFake = type(
    "ChatGoogleGenerativeAI", (_FakePatchModel,), {}
)
ChatGoogleGenerativeAIInvalidPatchFake = type(
    "ChatGoogleGenerativeAI", (_FakeInvalidPatchModel,), {}
)


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


class _RetryingDraftPlanner(ScriptedPlanner):
    def __init__(self, *, responses: list[AIMessage], drafted_plans: list[DraftedPatchPlan]):
        super().__init__(responses=responses)
        self._drafted_plans = list(drafted_plans)

    def draft_patch_preview(self, **_kwargs):
        if not self._drafted_plans:
            raise RuntimeError("Retrying draft planner ran out of drafted plans")
        return self._drafted_plans.pop(0)


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


def test_materialize_state_snapshot_strips_reset_markers():
    snapshot = materialize_state_snapshot(
        {
            "available_documents": reset_list_state(),
            "document_summaries": reset_dict_state(),
            "search_results": reset_list_state(),
            "selected_document_ids": ["7"],
        }
    )

    assert snapshot["available_documents"] == []
    assert snapshot["document_summaries"] == {}
    assert snapshot["search_results"] == []
    assert snapshot["selected_document_ids"] == ["7"]


def test_provider_runtime_kwargs_disable_google_afc():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )

    kwargs = planner._provider_runtime_kwargs_for_model(
        ChatGoogleGenerativeAIFake()
    )

    assert kwargs["automatic_function_calling"].disable is True


def test_langsmith_trace_config_uses_role_friendly_names():
    planner_config = LangChainCopilotPlanner._langsmith_trace_config(
        role="planner",
        operation="tool_calling",
        provider_spec=LlmProviderSpec(
            provider_family="openai",
            model_name="gpt-5.4-mini",
        ),
    )
    drafter_config = LangChainCopilotPlanner._langsmith_trace_config(
        role="drafter",
        operation="structured_output",
        provider_spec=LlmProviderSpec(
            provider_family="google",
            model_name="gemini-2.5-flash",
            google_location="us-east1",
        ),
    )

    # Without iteration/tool_names the planner label stays minimal.
    assert planner_config["run_name"] == "Planner"
    assert planner_config["metadata"]["llm_role"] == "planner"
    assert planner_config["metadata"]["model_name"] == "gpt-5.4-mini"
    assert "tool_calling" in planner_config["tags"]
    # Drafter always appends → structured_output even without iteration.
    assert drafter_config["run_name"] == "Drafter → structured_output"
    assert drafter_config["metadata"]["llm_role"] == "drafter"
    assert drafter_config["metadata"]["google_location"] == "us-east1"


def test_langsmith_trace_config_includes_iteration_and_tool_names():
    cfg = LangChainCopilotPlanner._langsmith_trace_config(
        role="planner",
        operation="tool_calling",
        provider_spec=LlmProviderSpec(provider_family="anthropic", model_name="claude-haiku-4-5"),
        iteration=3,
        tool_names=["read_document", "set_edit_plan"],
    )
    assert cfg["run_name"] == "Planner [i=3] → read_document, set_edit_plan"
    assert cfg["metadata"]["iteration"] == 3

    drafter_cfg = LangChainCopilotPlanner._langsmith_trace_config(
        role="drafter",
        operation="structured_output",
        provider_spec=LlmProviderSpec(provider_family="anthropic", model_name="claude-haiku-4-5"),
        iteration=3,
    )
    assert drafter_cfg["run_name"] == "Drafter [i=3] → structured_output"
    assert drafter_cfg["metadata"]["iteration"] == 3


def test_planner_system_instruction_enforces_sequential_tool_dependencies():
    instruction = LangChainCopilotPlanner._planner_system_instruction()

    assert "Fase 1 (Obligatoria): Leer el contexto." in instruction
    assert "varias herramientas no-write en paralelo" in instruction
    assert "read_* y propose_* en el mismo turno" in instruction
    assert "Solo puedes proponer una edicion por turno" in instruction
    assert 'read_document(mode="full")' in instruction
    assert DOCUMENTS_ARE_DATA_RULE in instruction


def test_patch_system_instruction_treats_clinical_context_as_data():
    instruction = LangChainCopilotPlanner._patch_system_instruction(
        requested_tool_name="propose_replace_span"
    )

    assert "La tool solicitada fue propose_replace_span." in instruction
    assert "exactText + prefixText + suffixText" in instruction
    assert "No uses anchors largos" in instruction
    assert DOCUMENTS_ARE_DATA_RULE in instruction
    assert "Si el contexto es ambiguo o insuficiente, no inventes contenido clinico." in instruction


def test_delete_patch_preview_allows_empty_content_preview():
    preview = {
        "patch_id": "patch-1",
        "target_document_id": "7",
        "target_document_title": "Nota clinica",
        "target_selection_reason": "llm_target_document_id",
        "base_version": 1,
        "operation_type": "delete_span",
        "content_preview": "",
    }

    assert tool_patch_preview_is_valid(preview) is True
    assert node_patch_preview_is_valid(preview) is True


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


def test_duplicate_singleton_tool_calls_are_deduped():
    message = make_ai_response("")
    message = message.model_copy(
        update={
            "tool_calls": [
                {"name": "list_open_documents", "args": {}, "id": "call-1", "type": "tool_call"},
                {"name": "list_open_documents", "args": {}, "id": "call-2", "type": "tool_call"},
                {
                    "name": "list_encounter_documents",
                    "args": {},
                    "id": "call-3",
                    "type": "tool_call",
                },
                {
                    "name": "list_encounter_documents",
                    "args": {},
                    "id": "call-4",
                    "type": "tool_call",
                },
            ]
        }
    )

    filtered = _filter_parallel_tool_calls(message)

    assert [tool_call["name"] for tool_call in filtered.tool_calls] == [
        "list_open_documents",
        "list_encounter_documents",
    ]


def test_parallel_search_tool_calls_keep_distinct_queries():
    message = make_ai_response("")
    message = message.model_copy(
        update={
            "tool_calls": [
                {
                    "name": "search_documents",
                    "args": {"query": "abdomen", "max_results": 1},
                    "id": "call-1",
                    "type": "tool_call",
                },
                {
                    "name": "search_documents",
                    "args": {"query": "egreso", "max_results": 1},
                    "id": "call-2",
                    "type": "tool_call",
                },
            ]
        }
    )

    filtered = _filter_parallel_tool_calls(message)

    assert [tool_call["args"]["query"] for tool_call in filtered.tool_calls] == [
        "abdomen",
        "egreso",
    ]


def test_patch_drafting_uses_only_json_schema():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._patch_model = ChatGoogleGenerativeAIPatchFake(
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
                    inserted_text="Fecha: 2 abril 2026\n\n",
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
    # run_name now includes iteration (i=1 when state has no iteration_count) and role suffix.
    assert planner._patch_model.runnables[0].configs[0]["run_name"] == "Drafter [i=1] → structured_output"
    assert all(
        runnable.invocation_kwargs == [{}]
        for runnable in planner._patch_model.runnables
        if runnable.invocation_kwargs
    )


def test_planner_tool_calling_trace_is_named_planner():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._planner_model = _FakePlannerModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_document",
                    "args": {"document_id": "99", "mode": "full"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )
    )

    response = planner.invoke_model(
        state=build_state("lee la nota"),
        messages=[HumanMessage(content="lee la nota")],
        tools=build_graph_tools(
            tools_client=FakeToolsClient(),
            planner=ScriptedPlanner(responses=[]),
        ),
    )

    assert response.tool_calls
    # run_name now includes iteration (i=1 when state has no prior iteration_count).
    assert planner._planner_model.runnables[0].configs[0]["run_name"] == "Planner [i=1]"


def test_planner_binds_sanitized_tool_specs_without_runtime_field():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    fake_model = _FakePlannerModel(make_ai_response("Listo."))
    planner._planner_model = fake_model

    planner.invoke_model(
        state=build_state("resume el encounter"),
        messages=[HumanMessage(content="resume el encounter")],
        tools=build_graph_tools(
            tools_client=FakeToolsClient(),
            planner=ScriptedPlanner(responses=[]),
        ),
    )

    assert isinstance(fake_model.bound_tools, list)
    read_summary_tool = next(
        tool
        for tool in fake_model.bound_tools
        if tool.get("function", {}).get("name") == "read_document_summary"
    )
    parameters = read_summary_tool["function"]["parameters"]
    assert "runtime" not in parameters.get("properties", {})
    assert "document_id" in parameters.get("properties", {})


def test_patch_drafting_fails_closed_without_function_calling_fallback():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._patch_model = ChatGoogleGenerativeAIInvalidPatchFake(
        RuntimeError("Invalid json output")
    )

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


def test_planner_empty_response_after_full_read_falls_back_to_single_proposal_tool_call():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._planner_model = _FakePlannerModel(AIMessage(content=""))

    state = build_state("agrega fiebre y dolor lumbar a la historia clinica")
    state["read_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "read_mode": "full",
        }
    ]

    response = planner.invoke_model(
        state=state,
        messages=[HumanMessage(content=state["user_message"])],
        tools=build_graph_tools(
            tools_client=FakeToolsClient(),
            planner=ScriptedPlanner(responses=[]),
        ),
    )

    assert response.tool_calls
    assert response.tool_calls[0]["name"] == "propose_replace_span"
    assert response.tool_calls[0]["args"]["target_document_id"] == "99"
    assert (
        response.tool_calls[0]["args"]["instruction"]
        == "agrega fiebre y dolor lumbar a la historia clinica"
    )


def test_planner_empty_response_after_non_edit_read_returns_text_instead_of_failing():
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._planner_model = _FakePlannerModel(AIMessage(content=""))

    state = build_state("resume la historia clinica")
    state["read_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "read_mode": "full",
        }
    ]

    response = planner.invoke_model(
        state=state,
        messages=[HumanMessage(content=state["user_message"])],
        tools=build_graph_tools(
            tools_client=FakeToolsClient(),
            planner=ScriptedPlanner(responses=[]),
        ),
    )

    assert response.tool_calls == []
    assert "Lei el documento disponible" in str(response.content)


def test_planner_empty_after_drafter_failure_returns_text_not_propose():
    """When the drafter just failed (last_tool_error indicates json_schema/patch failure),
    the fallback must NOT re-propose propose_* — that would loop into another drafter
    failure. Instead it should return user-facing text."""
    planner = LangChainCopilotPlanner(
        settings=SimpleNamespace(
            gcp_project_id="demo",
            gcp_region="us-central1",
            vertex_model="gemini-2.5-flash",
        ),
    )
    planner._planner_model = _FakePlannerModel(AIMessage(content=""))

    state = build_state("agrega fiebre a la nota")
    state["read_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "read_mode": "full",
        }
    ]
    # Simulate that the drafter just failed on the previous tool call
    state["last_tool_error"] = (
        "No pude redactar un patch clinico seguro: patch drafting failed "
        "with json_schema structured output: Invalid json output"
    )

    response = planner.invoke_model(
        state=state,
        messages=[HumanMessage(content=state["user_message"])],
        tools=build_graph_tools(
            tools_client=FakeToolsClient(),
            planner=ScriptedPlanner(responses=[]),
        ),
    )

    # Must NOT propose again — that would loop into the same drafter failure
    assert response.tool_calls == []
    assert "No pude materializar" in str(response.content)


def test_planner_empty_recovery_prompt_after_drafter_failure_avoids_propose():
    """The recovery prompt should tell the planner to NOT call propose_* when
    the last tool error was a drafter failure."""
    state = build_state("agrega fiebre al diagnostico")
    state["read_documents"] = [
        {
            "document_id": "42",
            "title": "Nota clinica",
            "type": "note",
            "read_mode": "full",
        }
    ]
    state["last_tool_error"] = "No pude redactar un patch clinico seguro: boom"

    prompt = LangChainCopilotPlanner._empty_response_recovery_prompt(state)
    assert "NO vuelvas a llamar propose" in prompt
    assert "propose_replace_span" not in prompt


def test_last_error_is_drafter_failure_detects_known_markers():
    assert LangChainCopilotPlanner._last_error_is_drafter_failure(
        {"last_tool_error": "No pude redactar un patch clinico seguro: json_schema error"}
    )
    assert LangChainCopilotPlanner._last_error_is_drafter_failure(
        {"last_tool_error": "patch drafting failed with json_schema: truncated"}
    )
    assert LangChainCopilotPlanner._last_error_is_drafter_failure(
        {"last_tool_error": "RECURSO DE IA AGOTADO (429)"}
    )
    assert not LangChainCopilotPlanner._last_error_is_drafter_failure(
        {"last_tool_error": "Document not found for id 99"}
    )
    assert not LangChainCopilotPlanner._last_error_is_drafter_failure(
        {"last_tool_error": None}
    )
    assert not LangChainCopilotPlanner._last_error_is_drafter_failure({})


def test_drafted_patch_schema_rejects_tool_names_and_defaults_rationale():
    valid_plan = DraftedPatchPlan.model_validate(
        {
            "patches": [
                {
                    "operation_type": "insert_after_span",
                    "anchor": {
                        "exactText": "Paciente estable.",
                    },
                    "inserted_text": "Fecha: 24/07/2024\n",
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
                    "anchor": {
                        "exactText": "Paciente estable.",
                    },
                    "inserted_text": "Fecha: 24/07/2024\n",
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


def _workspace_doc(
    *,
    version: int = 3,
    has_user_edits: bool = False,
    has_streaming_state: bool = False,
    has_pending_patches: bool = False,
    content_markdown: str | None = None,
) -> dict:
    document = {
        "document_id": "99",
        "title": "Nota clinica",
        "type": "note",
        "status": "draft",
        "source": "user",
        "ai_readable": True,
        "ai_writable": True,
        "version": version,
        "updated_at": "2026-04-02",
        "is_active": True,
        "is_open": True,
        "has_dirty_draft": False,
        "has_user_edits": has_user_edits,
        "has_streaming_state": has_streaming_state,
        "hidden_from_agent": False,
        "pinned_for_agent": False,
        "has_pending_patches": has_pending_patches,
    }
    if content_markdown is not None:
        document["content_markdown"] = content_markdown
    return document


def _without_reset_marker(items: list[dict]) -> list[dict]:
    return [item for item in items if not item.get("__reset__")]


def test_reset_transient_run_state_carries_fresh_full_read():
    state = build_state("continua")
    state["document_reads"] = [FakeToolsClient().read_document("99", mode="full")]
    state["document_summaries"] = {"99": FakeToolsClient().read_document_summary("99")}
    state["read_spans"] = [FakeToolsClient().read_document_span("99")]
    workspace_index = {
        **state["workspace_index"],
        "documents": [_workspace_doc(version=3)],
    }

    updates = _reset_transient_run_state(state=state, workspace_index=workspace_index)

    reads = _without_reset_marker(updates["document_reads"])
    spans = _without_reset_marker(updates["read_spans"])
    assert [read["document_id"] for read in reads] == ["99"]
    assert reads[0]["mode"] == "full"
    assert updates["document_summaries"]["99"]["version"] == 3
    assert spans[0]["document_id"] == "99"
    assert updates["read_documents"][0]["mode"] == "full"


def test_reset_transient_run_state_discards_stale_or_unsafe_reads():
    stale_state = build_state("continua")
    stale_state["document_reads"] = [FakeToolsClient().read_document("99", mode="full")]

    version_updates = _reset_transient_run_state(
        state=stale_state,
        workspace_index={
            **stale_state["workspace_index"],
            "documents": [_workspace_doc(version=4)],
        },
    )
    user_edit_updates = _reset_transient_run_state(
        state=stale_state,
        workspace_index={
            **stale_state["workspace_index"],
            "documents": [_workspace_doc(has_user_edits=True)],
        },
    )
    streaming_updates = _reset_transient_run_state(
        state=stale_state,
        workspace_index={
            **stale_state["workspace_index"],
            "documents": [_workspace_doc(has_streaming_state=True)],
        },
    )
    pending_patch_updates = _reset_transient_run_state(
        state=stale_state,
        workspace_index={
            **stale_state["workspace_index"],
            "documents": [_workspace_doc(has_pending_patches=True)],
        },
    )

    assert _without_reset_marker(version_updates["document_reads"]) == []
    assert _without_reset_marker(user_edit_updates["document_reads"]) == []
    assert _without_reset_marker(streaming_updates["document_reads"]) == []
    assert _without_reset_marker(pending_patch_updates["document_reads"]) == []


def test_reset_transient_run_state_preseed_replaces_cached_full_read():
    state = build_state("continua")
    state["document_reads"] = [FakeToolsClient().read_document("99", mode="full")]
    workspace_index = {
        **state["workspace_index"],
        "documents": [
            _workspace_doc(
                version=3,
                content_markdown="Contenido canonico fresco desde workspace.",
            )
        ],
    }

    updates = _reset_transient_run_state(state=state, workspace_index=workspace_index)

    reads = _without_reset_marker(updates["document_reads"])
    assert len(reads) == 1
    assert reads[0]["content"] == "Contenido canonico fresco desde workspace."
    assert updates["read_documents"][0]["content"] == "Contenido canonico fresco desde workspace."


def test_reset_transient_run_state_moves_active_errors_to_run_memory_notes():
    state = build_state("continua")
    state["last_tool_error"] = "El anchor es ambiguo; agrega prefixText."
    state["run_error"] = "No pude completar el run anterior."

    updates = _reset_transient_run_state(
        state=state,
        workspace_index=state["workspace_index"],
    )

    assert updates["last_tool_error"] is None
    assert updates["run_error"] is None
    assert {
        "source": "last_tool_error",
        "message": "El anchor es ambiguo; agrega prefixText.",
    } in updates["run_memory_notes"]
    assert {
        "source": "run_error",
        "message": "No pude completar el run anterior.",
    } in updates["run_memory_notes"]


def test_same_thread_preserves_fresh_full_read_for_set_edit_plan_auto_draft():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document",
                args={"document_id": "99", "mode": "full"},
                tool_call_id="call-1",
            ),
            make_ai_response("Documento leído."),
            make_ai_tool_call(
                tool_name="set_edit_plan",
                args={
                    "edit_scope": "propagation",
                    "clinical_impact_level": "factual",
                    "affected_sections": ["analisis_clinico"],
                    "needs_full_note": True,
                    "needs_external_knowledge": False,
                },
                tool_call_id="call-2",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Propagar edad correcta.",
            document_preview_after="Paciente estable, edad corregida.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="hash-demo",
                    replacement_text="Paciente estable, edad corregida.",
                    rationale="Corregir edad en analisis.",
                    section="analisis_clinico",
                ),
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
        checkpointer=InMemorySaver(),
    )
    thread_id = "copilot:encounter:12:doctor:7:chat:fresh-cache"
    first_state = build_state("lee la nota")
    first_state["workspace_index"]["documents"] = [_workspace_doc()]
    second_state = build_state("corrige la edad en toda la nota")
    second_state["workspace_index"]["documents"] = [_workspace_doc()]

    graph.invoke(first_state, config={"configurable": {"thread_id": thread_id}})
    next_state = graph.invoke(second_state, config={"configurable": {"thread_id": thread_id}})

    assert next_state["requires_human_review"] is True
    assert next_state["patch_set_preview"]["affected_sections"] == ["analisis_clinico"]
    assert [call["tool_name"] for call in next_state["tool_calls"]] == [
        "set_edit_plan",
    ]


def test_pending_edit_plan_reads_full_note_instead_of_finishing_with_text():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document_summary",
                args={"document_id": "99"},
                tool_call_id="call-1",
            ),
            make_ai_response("Resumen leído."),
            make_ai_tool_call(
                tool_name="set_edit_plan",
                args={
                    "edit_scope": "propagation",
                    "clinical_impact_level": "factual",
                    "affected_sections": ["analisis_clinico"],
                    "needs_full_note": True,
                    "needs_external_knowledge": False,
                },
                tool_call_id="call-2",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Propagar edad correcta.",
            document_preview_after="Paciente estable, edad corregida.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="hash-demo",
                    replacement_text="Paciente estable, edad corregida.",
                    rationale="Corregir edad en analisis.",
                    section="analisis_clinico",
                ),
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
        checkpointer=InMemorySaver(),
    )
    thread_id = "copilot:encounter:12:doctor:7:chat:pending-plan-read"
    first_state = build_state("lee resumen de la nota")
    first_state["workspace_index"]["documents"] = [_workspace_doc()]
    second_state = build_state("corrige la edad en toda la nota")
    second_state["workspace_index"]["documents"] = [_workspace_doc()]

    graph.invoke(first_state, config={"configurable": {"thread_id": thread_id}})
    next_state = graph.invoke(second_state, config={"configurable": {"thread_id": thread_id}})

    assert next_state["requires_human_review"] is True
    assert [call["tool_name"] for call in next_state["tool_calls"]] == [
        "set_edit_plan",
        "read_document",
    ]
    assert next_state["tool_calls"][1]["tool_input"] == {
        "document_id": "99",
        "mode": "full",
    }


def test_pending_edit_plan_uses_active_writable_target_when_no_read_exists():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="set_edit_plan",
                args={
                    "edit_scope": "propagation",
                    "clinical_impact_level": "factual",
                    "affected_sections": ["datos_demograficos"],
                    "needs_full_note": True,
                    "needs_external_knowledge": False,
                },
                tool_call_id="call-1",
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Corregir edad en datos demograficos.",
            document_preview_after="Paciente de 50 años.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="hash-demo",
                    replacement_text="Paciente de 50 años.",
                    rationale="Corregir edad.",
                    section="datos_demograficos",
                ),
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )
    state = build_state("en la historia clinica cambia la edad del paciente a 50 años")
    state["workspace_index"]["documents"] = [_workspace_doc()]

    next_state = graph.invoke(
        state,
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is True
    assert [call["tool_name"] for call in next_state["tool_calls"]] == [
        "set_edit_plan",
        "read_document",
    ]
    assert next_state["patch_set_preview"]["target_document_id"] == "99"


def test_direct_propose_incomplete_scope_retries_once_and_opens_review():
    planner = _RetryingDraftPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="propose_replace_span",
                args={
                    "target_document_id": "99",
                    "instruction": "Corrige la edad a 67 años en todas sus menciones.",
                    "affected_sections": [
                        "datos_demograficos",
                        "enfermedad_actual",
                        "impresion_diagnostica",
                    ],
                },
                tool_call_id="call-1",
            ),
        ],
        drafted_plans=[
            DraftedPatchPlan(
                rationale="Primer intento incompleto.",
                document_preview_after="Paciente estable y con mejoria.",
                patches=[
                    DraftedPatch(
                        operation_type="replace_span",
                        anchor={"exactText": "Paciente estable y con mejoria."},
                        expected_hash="preseed-hash",
                        replacement_text="Paciente de 67 años estable y con mejoria.",
                        rationale="Corregir edad en datos demográficos.",
                        section="datos_demograficos",
                    ),
                    DraftedPatch(
                        operation_type="replace_span",
                        anchor={"exactText": "Paciente estable y con mejoria."},
                        expected_hash="preseed-hash",
                        replacement_text="Paciente de 67 años estable y con mejoria.",
                        rationale="Corregir edad en enfermedad actual.",
                        section="enfermedad_actual",
                    ),
                ],
            ),
            DraftedPatchPlan(
                rationale="Segundo intento cubre todas las secciones revisadas.",
                document_preview_after="Paciente estable y con mejoria.",
                patches=[
                    DraftedPatch(
                        operation_type="replace_span",
                        anchor={"exactText": "Paciente estable y con mejoria."},
                        expected_hash="preseed-hash",
                        replacement_text="Paciente de 67 años estable y con mejoria.",
                        rationale="Corregir edad en datos demográficos.",
                        section="datos_demograficos",
                    ),
                    DraftedPatch(
                        operation_type="replace_span",
                        anchor={"exactText": "Paciente estable y con mejoria."},
                        expected_hash="preseed-hash",
                        replacement_text="Paciente de 67 años estable y con mejoria.",
                        rationale="Corregir edad en enfermedad actual.",
                        section="enfermedad_actual",
                    ),
                ],
                section_outcomes=[
                    DraftedSectionOutcome(
                        section="impresion_diagnostica",
                        status="no_change_needed",
                        rationale="La sección no contiene una mención de edad que requiera corrección.",
                    )
                ],
            ),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )
    state = build_state("corrige la edad a 67 años en toda la historia")
    state["workspace_index"]["documents"] = [
        _workspace_doc(
            version=3,
            content_markdown="Paciente estable y con mejoria.",
        )
    ]

    next_state = graph.invoke(
        state,
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7:retry-scope"}},
    )

    assert next_state["requires_human_review"] is True
    assert next_state["patch_set_preview"]["affected_sections"] == [
        "datos_demograficos",
        "enfermedad_actual",
        "impresion_diagnostica",
    ]
    assert len(next_state["patch_set_preview"]["patches"]) == 2
    assert next_state["patch_set_preview"]["section_outcomes"] == [
        {
            "section": "impresion_diagnostica",
            "status": "no_change_needed",
            "rationale": "La sección no contiene una mención de edad que requiera corrección.",
        }
    ]
    assert next_state["patch_validation_retry_used"] is False


def test_summary_request_uses_tool_loop_with_minimal_reads():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Necesito ver los documentos abiertos primero.",
            ),
            make_ai_tool_call(
                tool_name="list_encounter_documents",
                args={},
                tool_call_id="call-2",
                content="Necesito una vista de todos los documentos.",
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
        "list_encounter_documents",
        "search_documents",
        "read_document_span",
    ]
    assert len(next_state["read_documents"]) >= 1
    assert any(document["document_id"] == "55" for document in next_state["read_documents"])


def test_parallel_non_write_batch_updates_state_without_graph_race():
    planner = ScriptedPlanner(
        responses=[
            AIMessage(
                content="Leeré varias fuentes en paralelo antes de responder.",
                tool_calls=[
                    {"name": "list_open_documents", "args": {}, "id": "call-1", "type": "tool_call"},
                    {
                        "name": "list_encounter_documents",
                        "args": {},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                    {
                        "name": "read_document_summary",
                        "args": {"document_id": "99"},
                        "id": "call-3",
                        "type": "tool_call",
                    },
                    {
                        "name": "read_document_span",
                        "args": {"document_id": "55", "max_chars": 500},
                        "id": "call-4",
                        "type": "tool_call",
                    },
                    {
                        "name": "search_documents",
                        "args": {"query": "abdomen", "max_results": 1},
                        "id": "call-5",
                        "type": "tool_call",
                    },
                    {
                        "name": "search_documents",
                        "args": {"query": "egreso", "max_results": 1},
                        "id": "call-6",
                        "type": "tool_call",
                    },
                ],
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
        "list_encounter_documents",
        "read_document_summary",
        "read_document_span",
        "search_documents",
        "search_documents",
    ]
    assert next_state["document_summaries"]["99"]["document_id"] == "99"
    assert any(document["document_id"] == "55" for document in next_state["read_documents"])
    assert [result["query"] for result in next_state["search_results"]] == [
        "abdomen",
        "egreso",
    ]
    assert next_state["search_query"] is None
    assert next_state["last_tool_error"] is None


def test_parallel_batch_preserves_error_when_one_tool_fails():
    planner = ScriptedPlanner(
        responses=[
            AIMessage(
                content="Haré dos lecturas y una puede fallar.",
                tool_calls=[
                    {
                        "name": "read_document_summary",
                        "args": {"document_id": "404"},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "search_documents",
                        "args": {"query": "abdomen", "max_results": 1},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                ],
            ),
            make_ai_response("Intento completado."),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("Busca abdomen y trata de leer un resumen"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Intento completado."
    assert "No pude leer el resumen del documento 404" in str(next_state["last_tool_error"])
    assert [result["query"] for result in next_state["search_results"]] == ["abdomen"]


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
    assert "document_id" in tool_schemas["read_document"].get("properties", {})
    assert "mode" in tool_schemas["read_document"].get("properties", {})
    assert "document_id" in tool_schemas["read_document_summary"].get("properties", {})
    assert "document_id" in tool_schemas["read_document_span"].get("properties", {})
    assert "target_document_id" in tool_schemas["propose_replace_span"].get(
        "properties",
        {},
    )
    assert "target_document_id" in tool_schemas["propose_insert_before"].get(
        "properties",
        {},
    )
    assert "target_document_id" in tool_schemas["propose_delete_span"].get(
        "properties",
        {},
    )
    assert tool_schemas["list_open_documents"].get("properties", {}) == {}
    propose_replace_tool = next(tool for tool in tools if tool.name == "propose_replace_span")
    propose_insert_tool = next(
        tool for tool in tools if tool.name == "propose_insert_after_span"
    )
    propose_insert_before_tool = next(
        tool for tool in tools if tool.name == "propose_insert_before"
    )
    assert "Sequential precondition" in (propose_replace_tool.description or "")
    assert "Never call this in the same turn as read tools" in (
        propose_insert_tool.description or ""
    )
    assert "read_document(mode=\"full\")" in (propose_insert_before_tool.description or "")

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


def test_read_document_full_populates_read_documents_state():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="read_document",
                args={"document_id": "99", "mode": "full"},
                tool_call_id="call-1",
                content="Necesito leer el documento completo.",
            ),
            make_ai_response("Listo."),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("lee la nota completa"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["final_response"] == "Listo."
    assert any(
        document["document_id"] == "99" and document["mode"] == "full"
        for document in next_state["read_documents"]
    )


def test_read_document_view_and_derived_reads_preserve_detected_sections():
    read_payload = {
        "document_id": "99",
        "title": "Nota clinica",
        "type": "note",
        "version": 3,
        "mode": "full",
        "content": "Paciente estable.",
        "content_hash": "hash-demo",
        "structure_mode": "structured",
        "sections": [
            {
                "section_id": "enfermedad_actual",
                "label": "Enfermedad actual",
                "heading": "Enfermedad actual",
                "normalized_heading": "enfermedad actual",
                "heading_level": 2,
                "heading_style": "markdown_heading",
                "resolution_source": "literal_heading",
                "start_offset": 0,
                "content_start_offset": 0,
                "end_offset": 120,
                "content_preview": "Paciente estable.",
            }
        ],
    }

    view = _read_document_view(read_payload)
    state = build_state("lee la nota completa")
    state["document_reads"] = [view]

    derived_reads = _derive_read_documents(state)

    assert view["structure_mode"] == "structured"
    assert view["sections"][0]["section_id"] == "enfermedad_actual"
    assert derived_reads[0]["structure_mode"] == "structured"
    assert derived_reads[0]["sections"][0]["section_id"] == "enfermedad_actual"


def test_full_document_read_can_unlock_insert_after_proposal():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="list_open_documents",
                tool_call_id="call-1",
                content="Primero necesito ubicar el documento objetivo.",
            ),
            make_ai_tool_call(
                tool_name="read_document",
                args={"document_id": "99", "mode": "full"},
                tool_call_id="call-2",
                content="Leeré el documento completo porque el cambio va al final.",
            ),
            make_ai_tool_call(
                tool_name="propose_insert_after_span",
                args={"target_document_id": "99"},
                tool_call_id="call-3",
                content="Con la lectura completa ya puedo proponer el insert al final.",
            ),
        ],
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("agrega mi nombre al final de la nota"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is True
    assert next_state["patch_set_preview"]["target_document_id"] == "99"
    assert next_state["patch_set_preview"]["base_hash"] == "hash-demo"


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
        "Antes de proponer un patch debes leer el documento target con "
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
                tool_name="list_encounter_documents",
                args={},
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
                    inserted_text="Fecha: 2 abril 2026\n\n",
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
                    inserted_text="Fecha: 2 abril 2026\n\n",
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
                    inserted_text="\n\nFirma:\nJuan Moreno",
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


def test_validate_drafted_plan_rejects_partial_propagation_plan():
    validation_error = _validate_drafted_plan_against_clinical_plan(
        drafted_plan=DraftedPatchPlan(
            rationale="Solo materialicé el primer cambio.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={
                        "exactText": "Paciente estable y con mejoria.",
                    },
                    replacement_text="Paciente con fiebre y con mejoria.",
                    rationale="Actualizar enfermedad actual.",
                    section=None,
                )
            ],
        ),
        clinical_plan={
            "edit_scope": "propagation",
            "affected_sections": [
                "enfermedad_actual",
                "analisis",
                "plan",
            ],
        },
    )

    assert validation_error is not None
    assert "patches sin section" in validation_error
    assert (
        "faltan secciones obligatorias sin patch ni section_outcome: "
        "enfermedad_actual, analisis, plan."
    ) in validation_error


def test_validate_drafted_plan_accepts_section_outcome_without_patch():
    validation_error = _validate_drafted_plan_against_clinical_plan(
        drafted_plan=DraftedPatchPlan(
            rationale="La edad solo aparece en dos secciones.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "80 años"},
                    replacement_text="67 años",
                    rationale="Corregir edad en datos demográficos.",
                    section="datos_demograficos",
                ),
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "80 años"},
                    replacement_text="67 años",
                    rationale="Corregir edad en enfermedad actual.",
                    section="enfermedad_actual",
                ),
            ],
            section_outcomes=[
                DraftedSectionOutcome(
                    section="impresion_diagnostica",
                    status="no_change_needed",
                    rationale="La sección no contiene una mención de edad que requiera corrección.",
                )
            ],
        ),
        clinical_plan={
            "edit_scope": "local",
            "affected_sections": [
                "datos_demograficos",
                "enfermedad_actual",
                "impresion_diagnostica",
            ],
        },
    )

    assert validation_error is None


def test_draft_patch_set_from_state_drops_individual_noop_patch_and_keeps_valid_patch_set():
    planner = ScriptedPlanner(
        drafted_patch=DraftedPatchPlan(
            rationale="El drafter emitió un replace válido y otro no-op.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente de 70 años"},
                    replacement_text="Paciente de 50 años",
                    rationale="Corregir edad en analisis clinico.",
                    section="analisis_clinico",
                ),
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente de 50 años"},
                    replacement_text="Paciente de 50 años",
                    rationale="No-op accidental.",
                    section="analisis_clinico",
                ),
            ],
        )
    )
    state = build_state("corrige la edad en analisis clinico")
    state["available_documents"] = [
        make_document(
            "99",
            title="Nota clinica",
            document_type="note",
            is_active=True,
            version=3,
        )
    ]
    state["document_summaries"] = {
        "99": FakeToolsClient().read_document_summary("99"),
    }
    state["document_reads"] = [
        FakeToolsClient().read_document("99", mode="full"),
    ]
    state["read_documents"] = [
        {
            **state["document_reads"][0],
        }
    ]

    result = draft_patch_set_from_state(
        planner=planner,
        state=state,
        tool_name="propose_replace_span",
        target_document_id="99",
        instruction="Corrige la edad solo en analisis_clinico.",
        affected_sections=["analisis_clinico"],
        retry_validation_error=True,
    )

    assert result["ok"] is True
    assert len(result["payload"]["patches"]) == 1
    assert result["payload"]["patches"][0]["replacement_text"] == "Paciente de 50 años"
    assert result["updates"]["patch_validation_retry_used"] is False


def test_draft_patch_set_from_state_retries_when_all_drafter_patches_are_noop_replace():
    planner = ScriptedPlanner(
        drafted_patch=DraftedPatchPlan(
            rationale="El drafter emitió solo replaces sin cambio.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente de 50 años"},
                    replacement_text="Paciente de 50 años",
                    rationale="No-op accidental.",
                    section="analisis_clinico",
                ),
            ],
        )
    )
    state = build_state("corrige la edad en analisis clinico")
    state["available_documents"] = [
        make_document(
            "99",
            title="Nota clinica",
            document_type="note",
            is_active=True,
            version=3,
        )
    ]
    state["document_summaries"] = {
        "99": FakeToolsClient().read_document_summary("99"),
    }
    state["document_reads"] = [
        FakeToolsClient().read_document("99", mode="full"),
    ]
    state["read_documents"] = [
        {
            **state["document_reads"][0],
        }
    ]

    result = draft_patch_set_from_state(
        planner=planner,
        state=state,
        tool_name="propose_replace_span",
        target_document_id="99",
        instruction="Corrige la edad solo en analisis_clinico.",
        affected_sections=["analisis_clinico"],
        retry_validation_error=True,
    )

    assert result["ok"] is False
    assert "El drafter devolvio solo patches replace_span sin cambio real en posiciones: 1." in result["error_message"]
    assert "Esto normalmente significa que el documento ya contiene el texto pedido" in result["error_message"]
    assert "si ya lo esta, responde al medico" in result["error_message"]
    assert result["updates"]["next_required_action"] == "draft_patch_set"
    assert result["updates"]["patch_validation_retry_used"] is True


def test_normalize_factual_replacements_filters_invalid_and_out_of_scope_items():
    normalized = _normalize_factual_replacements(
        [
            {
                "replacement_id": "edad_paciente",
                "find_text": "45 años",
                "replace_text": "46 años",
                "scope_sections": ["enfermedad_actual", "fuera_de_scope"],
            },
            {
                "replacement_id": "sin_scope_explicito",
                "find_text": "1 tableta",
                "replace_text": "2 tabletas",
                "scope_sections": [],
            },
            {
                "replacement_id": "texto_igual",
                "find_text": "estable",
                "replace_text": "estable",
                "scope_sections": ["enfermedad_actual"],
            },
            {
                "replacement_id": "solo_fuera",
                "find_text": "2024",
                "replace_text": "2025",
                "scope_sections": ["fuera_de_scope"],
            },
        ],
        allowed_sections=["enfermedad_actual", "analisis_clinico"],
    )

    assert normalized == [
        {
            "replacement_id": "edad_paciente",
            "find_text": "45 años",
            "replace_text": "46 años",
            "scope_sections": ["enfermedad_actual"],
        },
        {
            "replacement_id": "sin_scope_explicito",
            "find_text": "1 tableta",
            "replace_text": "2 tabletas",
            "scope_sections": ["enfermedad_actual", "analisis_clinico"],
        },
    ]


def test_direct_propose_with_affected_sections_passes_local_scope_guardrail():
    planner = ScriptedPlanner(
        drafted_patch=DraftedPatchPlan(
            rationale="Quitar bullets solo en analisis clinico.",
            document_preview_after="Paciente estable y con mejoria.",
            patches=[
                DraftedPatch(
                    operation_type="delete_span",
                    anchor={
                        "exactText": "Paciente estable y con mejoria.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 29,
                    },
                    expected_hash="hash-demo",
                    rationale="Quitar solo el bullet point.",
                    section="analisis_clinico",
                )
            ],
        )
    )
    state = build_state("en analisis clinico, quitale los bullets")
    state["available_documents"] = [
        make_document(
            "99",
            title="Nota clinica",
            document_type="note",
            is_active=True,
            version=3,
        )
    ]
    state["document_summaries"] = {
        "99": FakeToolsClient().read_document_summary("99"),
    }
    state["document_reads"] = [
        FakeToolsClient().read_document("99", mode="full"),
    ]
    state["read_documents"] = [
        {
            **state["document_reads"][0],
        }
    ]

    result = draft_patch_set_from_state(
        planner=planner,
        state=state,
        tool_name="propose_delete_span",
        target_document_id="99",
        instruction=(
            "En analisis_clinico, bloque presentes y ausentes, elimina solo los bullet "
            "points y no toques otras secciones."
        ),
        affected_sections=["analisis_clinico"],
    )

    assert result["ok"] is True
    assert result["payload"]["affected_sections"] == ["analisis_clinico"]
    assert result["payload"]["patches"][0]["section"] == "analisis_clinico"


def test_direct_propose_with_affected_sections_fails_closed_on_extra_section():
    planner = ScriptedPlanner(
        drafted_patch=DraftedPatchPlan(
            rationale="El drafter se salio del scope.",
            document_preview_after="Paciente estable y con mejoria.",
            patches=[
                DraftedPatch(
                    operation_type="delete_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="hash-demo",
                    rationale="Cambio correcto en analisis clinico.",
                    section="analisis_clinico",
                ),
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="hash-demo",
                    replacement_text="Paciente egresa estable.",
                    rationale="Cambio extra fuera de scope.",
                    section="plan",
                ),
            ],
        )
    )
    state = build_state("en analisis clinico, quitale los bullets")
    state["available_documents"] = [
        make_document(
            "99",
            title="Nota clinica",
            document_type="note",
            is_active=True,
            version=3,
        )
    ]
    state["document_summaries"] = {
        "99": FakeToolsClient().read_document_summary("99"),
    }
    state["document_reads"] = [
        FakeToolsClient().read_document("99", mode="full"),
    ]
    state["read_documents"] = [
        {
            **state["document_reads"][0],
        }
    ]

    result = draft_patch_set_from_state(
        planner=planner,
        state=state,
        tool_name="propose_delete_span",
        target_document_id="99",
        instruction="Quita los bullets solo en analisis_clinico.",
        affected_sections=["analisis_clinico"],
    )

    assert result["ok"] is False
    assert "sections fuera del plan clínico: plan." in result["error_message"]


def test_set_edit_plan_auto_drafts_without_second_planner_turn_when_full_note_is_ready():
    planner = ScriptedPlanner(
        drafted_patch=DraftedPatchPlan(
            rationale="Propagar cambio a analisis clinico y plan.",
            document_preview_after="Paciente estable y con mejoria.\n\nPlan actualizado.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="preseed-hash",
                    replacement_text="Paciente estable, sin bullets duplicados.",
                    rationale="Ajuste en analisis clinico.",
                    section="analisis_clinico",
                ),
                DraftedPatch(
                    operation_type="insert_after_span",
                    anchor={"exactText": "Paciente estable y con mejoria."},
                    expected_hash="preseed-hash",
                    inserted_text="\n\nPlan actualizado.",
                    rationale="Ajuste en plan.",
                    section="plan",
                ),
            ],
        )
    )
    state = build_state("propaga este cambio a analisis clinico y plan")
    workspace_document = {
        "document_id": "99",
        "title": "Nota clinica",
        "type": "note",
        "is_active": True,
        "is_open": True,
        "ai_writable": True,
        "pinned_for_agent": False,
        "version": 3,
        "content_markdown": "Paciente estable y con mejoria.",
        "content_hash": "preseed-hash",
    }
    state["workspace_index"]["documents"] = [
        workspace_document
    ]
    state["available_documents"] = [
        {
            "document_id": "99",
            "title": "Nota clinica",
            "type": "note",
            "is_active": True,
            "is_open": True,
            "ai_writable": True,
            "pinned_for_agent": False,
            "version": 3,
        }
    ]
    state["document_summaries"] = {
        "99": FakeToolsClient().read_document_summary("99"),
    }
    state["document_reads"] = [
        {
            **FakeToolsClient().read_document("99", mode="full"),
            "content_hash": "preseed-hash",
        }
    ]
    state["read_documents"] = [
        {
            **state["document_reads"][0],
        }
    ]
    state["clinical_plan"] = {
        "edit_scope": "propagation",
        "clinical_impact_level": "factual",
        "affected_sections": ["analisis_clinico", "plan"],
        "needs_full_note": True,
        "needs_external_knowledge": False,
        "reasoning": (
            "El cambio debe propagarse a analisis clinico y plan para dejar "
            "la nota coherente."
        ),
    }
    state["next_required_action"] = "draft_patch_set"
    state["planned_target_document_id"] = "99"

    assert route_after_tool_execution(state) == NODE_DRAFT_PATCH_FROM_PLAN

    draft_node = make_draft_patch_from_plan_node(planner)
    updates = draft_node(state)

    assert updates["requires_human_review"] is True
    assert updates["patch_set_preview"]["affected_sections"] == [
        "analisis_clinico",
        "plan",
    ]
    assert updates["next_required_action"] is None
    assert updates["patch_set_preview"]["patches"][0]["section"] == "analisis_clinico"


def test_partial_propagation_plan_fails_closed_before_review():
    planner = ScriptedPlanner(
        responses=[
            make_ai_tool_call(
                tool_name="set_edit_plan",
                args={
                    "edit_scope": "propagation",
                    "clinical_impact_level": "clinical",
                    "affected_sections": [
                        "enfermedad_actual",
                        "analisis",
                        "plan",
                    ],
                    "needs_full_note": True,
                    "needs_external_knowledge": False,
                },
                tool_call_id="call-1",
            ),
            make_ai_tool_call(
                tool_name="read_document",
                args={"document_id": "99", "mode": "full"},
                tool_call_id="call-2",
            ),
            make_ai_tool_call(
                tool_name="propose_replace_span",
                args={
                    "target_document_id": "99",
                    "instruction": (
                        "Actualizar enfermedad actual y propagar el nuevo dato a análisis y plan."
                    ),
                },
                tool_call_id="call-3",
            ),
            make_ai_response(
                "Necesito rehacer el patch set completo por secciones antes de enviarlo a revisión."
            ),
        ],
        drafted_patch=DraftedPatchPlan(
            rationale="Solo pude materializar el primer cambio.",
            document_preview_after="Paciente con fiebre y con mejoria.",
            patches=[
                DraftedPatch(
                    operation_type="replace_span",
                    anchor={
                        "exactText": "Paciente estable y con mejoria.",
                        "prefixText": "",
                        "suffixText": "",
                        "startOffset": 0,
                        "endOffset": 29,
                    },
                    expected_hash="hash-demo",
                    replacement_text="Paciente con fiebre y con mejoria.",
                    rationale="Actualizar solo enfermedad actual.",
                    section=None,
                )
            ],
        ),
    )
    graph = build_clinical_copilot_graph(
        tools_client=FakeToolsClient(),
        planner=planner,
    )

    next_state = graph.invoke(
        build_state("agrega fiebre y propagalo a analisis y plan"),
        config={"configurable": {"thread_id": "copilot:encounter:12:doctor:7"}},
    )

    assert next_state["requires_human_review"] is False
    assert next_state.get("patch_set_preview") is None
    assert next_state.get("patch_preview") is None
    assert next_state.get("run_error") is None
    assert (
        next_state["final_response"]
        == "Necesito rehacer el patch set completo por secciones antes de enviarlo a revisión."
    )
    assert any(
        "patch set incompleto para el plan clínico actual" in result["summary"]
        for result in next_state["tool_results"]
    )


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
