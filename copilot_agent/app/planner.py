from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence
from xml.sax.saxutils import escape

from google.genai import types as genai_types
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings

logger = logging.getLogger(__name__)


PatchOperationType = Literal[
    "replace_span",
    "insert_before",
    "insert_after_span",
    "delete_span",
    "rewrite_document",
]


class PlannerDecision(BaseModel):
    action_type: str
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str = ""
    response_content: str | None = None
    intent: str | None = None
    target_document_hint: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class DraftedPatchAnchor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exact_text: str = Field(
        ...,
        alias="exactText",
        description="The exact textual match in the document. MANDATORY. CRITICAL RULE: NEVER include newlines (\\n) or attempt to match large paragraphs. Pick a VERY SHORT, unique phrase (3-8 words) from a single line. The backend performs a strict substring search and will fail if JSON whitespace normalization alters your text."
    )
    prefix_text: str | None = Field(
        default=None, 
        alias="prefixText",
        description="A few words immediately BEFORE the exactText. CRITICAL: Do NOT include newlines (\\n) or invisible characters."
    )
    suffix_text: str | None = Field(
        default=None, 
        alias="suffixText",
        description="A few words immediately AFTER the exactText. CRITICAL: Do NOT include newlines (\\n) or invisible characters."
    )
    start_offset: int | None = Field(
        default=None, 
        alias="startOffset",
        description="The exact starting character index of the 'exact_text' in the document. Must always be provided if endOffset is provided."
    )
    end_offset: int | None = Field(
        default=None, 
        alias="endOffset",
        description="The exact ending character index of the 'exact_text' in the document. Must always be provided if startOffset is provided."
    )

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", by_alias=True, exclude_none=True)


class DraftedPatch(BaseModel):
    operation_type: PatchOperationType = Field(
        description=(
            "Patch operation constant. Must be one of: replace_span, insert_before, "
            "insert_after_span, delete_span, rewrite_document. Never use tool names like "
            "propose_replace_span. If the entire document must be changed, use rewrite_document."
        )
    )
    anchor: DraftedPatchAnchor = Field(default_factory=DraftedPatchAnchor)
    expected_hash: str | None = None
    before_preview: str | None = None
    after_preview: str | None = None
    document_preview_after: str | None = None
    content_preview: str
    rationale: str = Field(
        default="",
        description=(
            "Short clinical rationale for the patch. Leave empty only if the model "
            "cannot provide a concise rationale safely."
        ),
    )
    confidence: float | None = None


class DraftedPatchPlan(BaseModel):
    patches: list[DraftedPatch] = Field(default_factory=list)
    rationale: str | None = None
    document_preview_after: str | None = None


class CopilotPlanner(Protocol):
    def invoke_model(
        self,
        *,
        state: Mapping[str, Any],
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool | Callable[..., Any]],
    ) -> AIMessage: ...

    def draft_patch_preview(
        self,
        *,
        state: Mapping[str, Any],
        target_document: Mapping[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: Mapping[str, Any] | None = None,
        requested_tool_name: str | None = None,
    ) -> DraftedPatchPlan: ...


def _is_proposal_tool_name(tool_name: str | None) -> bool:
    return str(tool_name or "").startswith("propose_")


def _filter_parallel_tool_calls(message: AIMessage) -> AIMessage:
    tool_calls = list(message.tool_calls or [])
    if len(tool_calls) <= 1:
        return message

    # Allow parallel reads/searches, but keep proposal steps serialized. Proposal
    # tools mutate the single pending patch-set slot of the runtime, so mixing them
    # with reads or emitting several at once causes state races and speculative edits.
    proposal_calls = [
        tool_call for tool_call in tool_calls if _is_proposal_tool_name(tool_call.get("name"))
    ]
    non_proposal_calls = [
        tool_call for tool_call in tool_calls if not _is_proposal_tool_name(tool_call.get("name"))
    ]

    if proposal_calls and non_proposal_calls:
        logger.info(
            "Planner returned mixed read/propose tool calls in one turn; dropping %s proposal call(s) and keeping %s non-proposal call(s).",
            len(proposal_calls),
            len(non_proposal_calls),
        )
        return message.model_copy(update={"tool_calls": non_proposal_calls})

    if len(proposal_calls) > 1:
        logger.info(
            "Planner returned %s proposal tool calls in one turn; keeping only the first to avoid patch_set_preview overwrites.",
            len(proposal_calls),
        )
        return message.model_copy(update={"tool_calls": [proposal_calls[0]]})

    return message


def _shorten_text(value: Any, *, max_length: int = 320) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:max_length]


def _xml_line(tag: str, value: Any, *, max_length: int = 320) -> str:
    return f"<{tag}>{escape(_shorten_text(value, max_length=max_length))}</{tag}>"


def _render_documents(documents: Sequence[Mapping[str, Any]]) -> str:
    if not documents:
        return "<available_documents />"

    lines = ["<available_documents>"]
    for document in documents[:8]:
        lines.extend(
            [
                "  <document>",
                f"    {_xml_line('document_id', document.get('document_id'))}",
                f"    {_xml_line('title', document.get('title'))}",
                f"    {_xml_line('type', document.get('type'))}",
                f"    {_xml_line('status', document.get('status'))}",
                f"    {_xml_line('version', document.get('version'))}",
                f"    {_xml_line('is_active', document.get('is_active'))}",
                f"    {_xml_line('is_open', document.get('is_open'))}",
                f"    {_xml_line('ai_writable', document.get('ai_writable'))}",
                f"    {_xml_line('excerpt', document.get('excerpt'))}",
                "  </document>",
            ]
        )
    lines.append("</available_documents>")
    return "\n".join(lines)


def _render_document_summaries(document_summaries: Mapping[str, Mapping[str, Any]]) -> str:
    if not document_summaries:
        return "<document_summaries />"

    lines = ["<document_summaries>"]
    for document_id, summary in list(document_summaries.items())[:8]:
        lines.extend(
            [
                "  <document_summary>",
                f"    {_xml_line('document_id', document_id)}",
                f"    {_xml_line('title', summary.get('title'))}",
                f"    {_xml_line('type', summary.get('type'))}",
                f"    {_xml_line('version', summary.get('version'))}",
                f"    {_xml_line('short_summary', summary.get('short_summary'))}",
                f"    {_xml_line('excerpt', summary.get('excerpt'))}",
                "  </document_summary>",
            ]
        )
    lines.append("</document_summaries>")
    return "\n".join(lines)


def _render_read_spans(read_spans: Sequence[Mapping[str, Any]]) -> str:
    if not read_spans:
        return "<read_spans />"

    lines = ["<read_spans>"]
    for span in read_spans[:4]:
        lines.extend(
            [
                "  <read_span>",
                f"    {_xml_line('document_id', span.get('document_id'))}",
                f"    {_xml_line('title', span.get('title'))}",
                f"    {_xml_line('start_offset', span.get('start_offset'))}",
                f"    {_xml_line('end_offset', span.get('end_offset'))}",
                f"    {_xml_line('content', span.get('content'), max_length=900)}",
                "  </read_span>",
            ]
        )
    lines.append("</read_spans>")
    return "\n".join(lines)


def _render_context_view(context_view: Mapping[str, Any] | None) -> str:
    if not context_view:
        return "<context_view />"

    lines = ["<context_view>"]
    for fact in (context_view.get("facts") or [])[:6]:
        lines.extend(
            [
                "  <fact>",
                f"    {_xml_line('category', fact.get('category'))}",
                f"    {_xml_line('value', fact.get('value'))}",
                f"    {_xml_line('source_document_id', fact.get('source_document_id'))}",
                f"    {_xml_line('confidence', fact.get('confidence'))}",
                "  </fact>",
            ]
        )
    lines.append("</context_view>")
    return "\n".join(lines)


def _render_patch_history(patch_history: Mapping[str, list[Mapping[str, Any]]]) -> str:
    if not patch_history:
        return "<patch_history />"

    lines = ["<patch_history>"]
    for document_id, patches in list(patch_history.items())[:4]:
        lines.append(f'  <document_patches document_id="{escape(str(document_id))}">')
        for patch in patches[:4]:
            lines.extend(
                [
                    "    <patch>",
                    f"      {_xml_line('patch_id', patch.get('patch_id'))}",
                    f"      {_xml_line('status', patch.get('status'))}",
                    f"      {_xml_line('operation_type', patch.get('operation_type'))}",
                    f"      {_xml_line('rationale', patch.get('rationale'))}",
                    "    </patch>",
                ]
            )
        lines.append("  </document_patches>")
    lines.append("</patch_history>")
    return "\n".join(lines)


def _render_search_matches(search_matches: Sequence[Mapping[str, Any]]) -> str:
    if not search_matches:
        return "<search_matches />"

    lines = ["<search_matches>"]
    for match in search_matches[:4]:
        lines.extend(
            [
                "  <match>",
                f"    {_xml_line('document_id', match.get('document_id'))}",
                f"    {_xml_line('title', match.get('title'))}",
                f"    {_xml_line('score', match.get('score'))}",
                f"    {_xml_line('snippet', match.get('snippet'))}",
                "  </match>",
            ]
        )
    lines.append("</search_matches>")
    return "\n".join(lines)


def _render_turn_context(state: Mapping[str, Any]) -> str:
    workspace_index = state.get("workspace_index") or {}
    return "\n".join(
        [
            "<copilot_turn_context>",
            f"  {_xml_line('user_query', state.get('user_message'), max_length=1200)}",
            "  <workspace_index>",
            f"    {_xml_line('encounter_id', workspace_index.get('encounter_id'))}",
            f"    {_xml_line('workspace_version', workspace_index.get('workspace_version'))}",
            f"    {_xml_line('active_document_id', state.get('active_document_id'))}",
            f"    {_xml_line('selected_document_ids', ', '.join(state.get('selected_document_ids') or []))}",
            "  </workspace_index>",
            _render_documents(state.get("available_documents") or []),
            _render_document_summaries(state.get("document_summaries") or {}),
            _render_read_spans(state.get("read_spans") or []),
            _render_context_view(state.get("context_view")),
            _render_search_matches(state.get("search_matches") or []),
            _render_patch_history(state.get("patch_history") or {}),
            "  <budgets>",
            f"    {_xml_line('iteration_count', state.get('iteration_count'))}",
            f"    {_xml_line('max_iterations', state.get('max_iterations'))}",
            f"    {_xml_line('patch_operations_count', state.get('patch_operations_count'))}",
            f"    {_xml_line('max_patch_operations', state.get('max_patch_operations'))}",
            "  </budgets>",
            f"  {_xml_line('last_tool_error', state.get('last_tool_error'))}",
            f"  {_xml_line('last_planner_error', state.get('last_planner_error'))}",
            "</copilot_turn_context>",
        ]
    )


def _render_intent_context(state: Mapping[str, Any]) -> str:
    workspace_index = state.get("workspace_index") or {}
    return "\n".join(
        [
            "<intent_classification_input>",
            f"  {_xml_line('user_query', state.get('user_message'), max_length=1200)}",
            "  <workspace>",
            f"    {_xml_line('active_document_id', workspace_index.get('active_document_id'))}",
            f"    {_xml_line('open_document_ids', ', '.join(workspace_index.get('open_document_ids') or []))}",
            "  </workspace>",
            _render_documents(state.get("available_documents") or []),
            "</intent_classification_input>",
        ]
    )


def _render_patch_input(
    *,
    state: Mapping[str, Any],
    target_document: Mapping[str, Any],
    target_document_content: str,
    supporting_context: list[dict[str, Any]],
    span_payload: Mapping[str, Any] | None,
    requested_tool_name: str | None,
) -> str:
    lines = [
        "<patch_drafting_input>",
        f"  {_xml_line('user_query', state.get('user_message'), max_length=1400)}",
        f"  {_xml_line('requested_tool_name', requested_tool_name)}",
        "  <target_document>",
        f"    {_xml_line('document_id', target_document.get('document_id'))}",
        f"    {_xml_line('title', target_document.get('title'))}",
        f"    {_xml_line('type', target_document.get('type'))}",
        f"    {_xml_line('version', target_document.get('version'))}",
        "  </target_document>",
        f"  {_xml_line('target_document_content', target_document_content, max_length=4000)}",
    ]
    if span_payload:
        lines.extend(
            [
                "  <selected_span>",
                f"    {_xml_line('start_offset', span_payload.get('start_offset'))}",
                f"    {_xml_line('end_offset', span_payload.get('end_offset'))}",
                f"    {_xml_line('content_hash', span_payload.get('content_hash'))}",
                "  </selected_span>",
            ]
        )
    lines.append("  <supporting_context>")
    for item in supporting_context[:8]:
        lines.extend(
            [
                "    <context_item>",
                f"      {_xml_line('document_id', item.get('document_id'))}",
                f"      {_xml_line('title', item.get('title'))}",
                f"      {_xml_line('type', item.get('type'))}",
                f"      {_xml_line('read_mode', item.get('read_mode'))}",
                f"      {_xml_line('excerpt', item.get('excerpt'), max_length=800)}",
                "    </context_item>",
            ]
        )
    lines.extend(["  </supporting_context>", "</patch_drafting_input>"])
    return "\n".join(lines)


@dataclass
class LangChainCopilotPlanner:
    settings: Settings

    _planner_model: ChatGoogleGenerativeAI | None = None
    _patch_model: ChatGoogleGenerativeAI | None = None

    @staticmethod
    def _provider_runtime_kwargs() -> dict[str, Any]:
        # Keep the tool loop in our LangGraph runtime. Google AFC adds provider-side
        # orchestration for function calls, which we do not want in this clinical flow.
        return {
            "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(
                disable=True
            )
        }

    def invoke_model(
        self,
        *,
        state: Mapping[str, Any],
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool | Callable[..., Any]],
    ) -> AIMessage:
        runnable = self._planner_model_instance().bind_tools(tools)
        response = self._invoke_with_retry(
            "planner tool calling",
            lambda: runnable.invoke(
                [
                    SystemMessage(content=self._planner_system_instruction()),
                    HumanMessage(content=_render_turn_context(state)),
                    *messages,
                ],
                **self._provider_runtime_kwargs(),
            ),
        )
        if not isinstance(response, AIMessage):
            raise RuntimeError("Planner did not return an AIMessage")
        return _filter_parallel_tool_calls(response)

    def draft_patch_preview(
        self,
        *,
        state: Mapping[str, Any],
        target_document: Mapping[str, Any],
        target_document_content: str,
        supporting_context: list[dict[str, Any]],
        span_payload: Mapping[str, Any] | None = None,
        requested_tool_name: str | None = None,
    ) -> DraftedPatchPlan:
        messages = [
            SystemMessage(
                content=self._patch_system_instruction(
                    requested_tool_name=requested_tool_name,
                )
            ),
            HumanMessage(
                content=_render_patch_input(
                    state=state,
                    target_document=target_document,
                    target_document_content=target_document_content,
                    supporting_context=supporting_context,
                    span_payload=span_payload,
                    requested_tool_name=requested_tool_name,
                )
            ),
        ]
        result = self._invoke_patch_drafting(messages=messages)
        return self._normalize_patch_plan(self._validate_patch_plan_result(result))

    def _invoke_with_retry(
        self,
        label: str,
        operation: Callable[[], Any],
        *,
        attempts: int = 2,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return operation()
            except Exception as error:  # pragma: no cover - provider edge
                last_error = error
                logger.warning(
                    "LLM %s attempt %s/%s failed: %s",
                    label,
                    attempt,
                    attempts,
                    error,
                )
        assert last_error is not None
        raise RuntimeError(f"{label} failed after {attempts} attempts: {last_error}")

    def _invoke_patch_drafting(
        self,
        *,
        messages: Sequence[BaseMessage],
    ) -> Any:
        # Keep patch drafting on json_schema only. The provider-side function_calling
        # fallback proved noisier here: it increased remote calls, reintroduced AFC-like
        # behavior, and made Gemini more likely to echo tool names instead of patch enums.
        structured = self._patch_model_instance().with_structured_output(
            DraftedPatchPlan,
            method="json_schema",
        )
        try:
            return self._invoke_with_retry(
                "patch drafting via json_schema",
                lambda: structured.invoke(
                    messages,
                    **self._provider_runtime_kwargs(),
                ),
                attempts=1,
            )
        except Exception as error:  # pragma: no cover - provider edge
            raise RuntimeError(
                "patch drafting failed with json_schema structured output: "
                f"{error}"
            ) from error

    @staticmethod
    def _validate_patch_plan_result(result: Any) -> DraftedPatchPlan:
        # Fail closed with a clear runtime error instead of crashing later on
        # `result.patches` when the provider returns no structured payload.
        if result is None:
            raise RuntimeError(
                "El LLM no devolvio un DraftedPatchPlan estructurado en patch drafting."
            )
        if isinstance(result, DraftedPatchPlan):
            return result
        try:
            return DraftedPatchPlan.model_validate(result)
        except Exception as error:
            raise RuntimeError(
                "El LLM devolvio un DraftedPatchPlan invalido en patch drafting: "
                f"{error}"
            ) from error

    def _planner_model_instance(self) -> ChatGoogleGenerativeAI:
        if self._planner_model is None:
            self._planner_model = self._build_chat_model(
                temperature=0.1,
                max_tokens=700,
            )
        return self._planner_model

    def _patch_model_instance(self) -> ChatGoogleGenerativeAI:
        if self._patch_model is None:
            self._patch_model = self._build_chat_model(
                temperature=0.0,
                max_tokens=1600,
            )
        return self._patch_model

    def _build_chat_model(
        self,
        *,
        temperature: float,
        max_tokens: int,
    ) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=self.settings.vertex_model,
            vertexai=True,
            project=self.settings.gcp_project_id,
            location=self.settings.gcp_region,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=0,
            disable_streaming="tool_calling",
        )

    @staticmethod
    def _planner_system_instruction() -> str:
        return (
            "Eres el planner del copiloto clinico en un bounded tool loop. "
            "Debes responder directamente si no hacen falta tools. "
            "REGLA DE ORO: eres un agente secuencial estricto. "
            "Si necesitas herramientas, usa tool calling nativo. "
            "Puedes pedir varias herramientas de lectura o busqueda en paralelo solo cuando sean "
            "independientes entre si. "
            "No puedes anticipar resultados de herramientas futuras ni emitir varias herramientas "
            "dependientes en la misma respuesta. "
            "Si una edicion requiere leer y luego proponer, primero debes llamar una tool de lectura, "
            "esperar su resultado en el siguiente turno y solo entonces llamar la tool de proposal. "
            "Pedir read_* y propose_* en el mismo turno para el mismo documento es un error. "
            "Solo puedes proponer una edicion por turno y solo sobre un documento target a la vez. "
            "Minimiza lecturas redundantes. "
            "Antes de proponer un patch debes leer el documento target con read_document_summary "
            "y read_document_span en turnos previos ya completados. "
            "No escribas directamente el documento canonico. "
            "Si una tool devuelve un error, corrige la llamada o pide mas contexto; no inventes "
            "patches ni cierres una edicion con respuesta engañosa. "
            "Para saludos simples como 'hola', responde sin tools."
        )

    @staticmethod
    def _patch_system_instruction(*, requested_tool_name: str | None) -> str:
        requested_operation = requested_tool_name or "propose_replace_span"
        return (
            "Eres un redactor clinico que prepara patch sets revisables sobre un unico "
            "documento target. "
            "Debes producir un DraftedPatchPlan estructurado y seguro. "
            f"La tool solicitada fue {requested_operation}. "
            "La tool solicitada NO es el valor de operation_type. "
            "operation_type debe ser exactamente una de estas constantes: "
            "replace_span, insert_before, insert_after_span, delete_span. "
            "Nunca uses nombres de tools como propose_replace_span o "
            "propose_insert_after_span dentro del DraftedPatchPlan. "
            "Si el usuario pidio cambios en partes distintas del documento, devuelve varios "
            "patches ordenados de arriba hacia abajo. "
            "No copies literalmente la instruccion del medico dentro del documento. "
            "No uses placeholders como '[Ajuste sugerido]'. "
            "Cada patch debe incluir content_preview y, si es posible, una rationale breve. "
            "Si no puedes materializar cambios clinicamente seguros con el contexto disponible, "
            "devuelve patches vacio y explica el motivo en rationale. "
            "Mantén la redaccion medica fiel al documento y al pedido."
        )

    @staticmethod
    def _normalize_patch_plan(result: DraftedPatchPlan) -> DraftedPatchPlan:
        patches: list[DraftedPatch] = []
        for patch in result.patches:
            normalized_preview_after = (
                patch.document_preview_after or patch.content_preview or None
            )
            patches.append(
                patch.model_copy(
                    update={
                        "document_preview_after": normalized_preview_after,
                        "content_preview": patch.content_preview
                        or normalized_preview_after
                        or "",
                    }
                )
            )
        document_preview_after = result.document_preview_after
        if not document_preview_after and patches:
            document_preview_after = (
                patches[-1].document_preview_after or patches[-1].content_preview
            )
        return DraftedPatchPlan(
            patches=patches,
            rationale=result.rationale,
            document_preview_after=document_preview_after,
        )


def build_planner(settings: Settings) -> CopilotPlanner:
    return LangChainCopilotPlanner(settings=settings)
