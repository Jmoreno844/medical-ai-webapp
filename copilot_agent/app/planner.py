from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

from google.genai import types as genai_types
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.llm.context_rendering import render_patch_input, render_turn_context
from app.llm.instructions import patch_system_instruction, planner_system_instruction

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


class ClinicalPlan(BaseModel):
    """Señales estructuradas de alcance clínico emitidas por el planner antes de redactar patches.

    El planner llama `set_edit_plan` con estos campos cuando detecta que el cambio
    es de propagación o reinterpretación clínica. La tool escribe el plan al state y
    levanta `max_patch_operations` dinámicamente según `edit_scope`.

    Para ediciones simples (local edit: typo, inserción corta, borrado puntual), el planner
    puede ir directo a propose_* sin llamar set_edit_plan. El drafter operará con un solo patch.
    """

    edit_scope: Literal["local", "propagation", "reinterpretation"] = Field(
        description=(
            "Alcance del cambio. "
            "'local' = typo, inserción corta, borrado puntual sobre una sección. "
            "'propagation' = nuevo dato clínico que debe reflejarse en varias secciones. "
            "'reinterpretation' = el dato cambia análisis, impresión diagnóstica, riesgo o plan."
        )
    )
    clinical_impact_level: Literal["cosmetic", "factual", "clinical"] = Field(
        description=(
            "'cosmetic' = estilo, formato, traducción sin cambio de datos. "
            "'factual' = agrega o corrige un dato documentado (EG edad gestacional). "
            "'clinical' = cambia diagnóstico, análisis, riesgo o plan de manejo."
        )
    )
    affected_sections: list[str] = Field(
        default_factory=list,
        description=(
            "Secciones semánticas del documento que el drafter debe tocar. "
            "Usa nombres en snake_case del español clínico, por ejemplo: "
            "'enfermedad_actual', 'antecedentes_relevantes', 'impresion_diagnostica', "
            "'analisis_clinico', 'plan', 'revision_por_sistemas'. "
            "El drafter debe emitir al menos un patch por cada sección listada aquí."
        ),
    )
    needs_full_note: bool = Field(
        description=(
            "True si el cambio requiere leer la nota completa antes de proponer patches. "
            "Siempre True para propagation y reinterpretation. "
            "El runtime rechazará propose_* si este campo es True y no hay lectura 'full' previa."
        )
    )
    needs_external_knowledge: bool = Field(
        description=(
            "True si el cambio requiere conocimiento externo (guías clínicas, farmacología) "
            "que no está presente en la nota del encuentro. Señal para RAG futuro."
        )
    )
    should_propagate_to_analysis_and_plan: bool = Field(
        description=(
            "True si el nuevo dato clínico debe reflejarse en análisis clínico y/o plan de manejo."
        )
    )


class DraftedPatchAnchor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exact_text: str = Field(
        ...,
        alias="exactText",
        description="The exact textual match in the document. MANDATORY. Primary anchor signal. NEVER include newlines (\\n) or large paragraphs. Pick a VERY SHORT, unique phrase (3-8 words) from a single line. The backend performs a strict substring search and will fail if JSON whitespace normalization alters your text."
    )
    prefix_text: str | None = Field(
        default=None,
        alias="prefixText",
        description="A few words immediately BEFORE the exactText. Strongly recommended when the text could repeat. Do NOT include newlines (\\n) or invisible characters."
    )
    suffix_text: str | None = Field(
        default=None,
        alias="suffixText",
        description="A few words immediately AFTER the exactText. Strongly recommended when the text could repeat. Do NOT include newlines (\\n) or invisible characters."
    )
    start_offset: int | None = Field(
        default=None,
        alias="startOffset",
        description="Optional secondary hint. The exact starting character index of the 'exact_text' in the document. Must always be provided if endOffset is provided."
    )
    end_offset: int | None = Field(
        default=None,
        alias="endOffset",
        description="Optional secondary hint. The exact ending character index of the 'exact_text' in the document. Must always be provided if startOffset is provided."
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
    # Sección semántica del documento a la que pertenece este patch.
    # Debe coincidir con uno de los valores en ClinicalPlan.affected_sections.
    # Permite al frontend y al auditor clínico entender qué parte de la nota se está tocando.
    section: str | None = Field(
        default=None,
        description=(
            "Sección semántica del documento a la que pertenece este patch. "
            "Debe coincidir con uno de los valores de affected_sections del plan clínico. "
            "Ejemplos: 'antecedentes_relevantes', 'plan', 'impresion_diagnostica'."
        ),
    )


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
        requested_tool_instruction: str | None = None,
    ) -> DraftedPatchPlan: ...


def _is_proposal_tool_name(tool_name: str | None) -> bool:
    return str(tool_name or "").startswith("propose_")


def _tool_call_identity(tool_call: dict[str, Any]) -> tuple[str, str]:
    tool_name = str(tool_call.get("name") or "")
    if tool_name in {
        "list_open_documents",
        "list_encounter_documents",
    }:
        return tool_name, "__singleton__"
    return tool_name, json.dumps(tool_call.get("args") or {}, sort_keys=True, separators=(",", ":"))


def _filter_parallel_tool_calls(message: AIMessage) -> AIMessage:
    # Gemini sometimes proposes writes (propose_*) to multiple documents in one
    # turn when the planner is given a broad instruction. Parallel clinical writes
    # are unsafe here: each propose_* call drafts a full patch set, and running
    # two propose_* in the same batch would produce two independent patch sets
    # with no ordering guarantee. We keep only the first proposal; the doctor can
    # request subsequent edits in the next turn.
    # Read-only calls (list_*, read_*) are safe to parallelize and are not filtered.
    #
    # NOTE: this filter was also the root cause of a secondary bug where the planner
    # tried to call propose_replace_span 5 times (one per inline replacement) and
    # 4 were silently dropped. The fix is ProposePatchInput.instruction: the planner
    # now encodes ALL intended replacements for a document in a single call, and the
    # drafter materializes them as multiple patches[]. See tools.py ProposePatchInput.
    tool_calls = list(message.tool_calls or [])
    if len(tool_calls) <= 1:
        return message

    proposal_calls = [
        tool_call for tool_call in tool_calls if _is_proposal_tool_name(tool_call.get("name"))
    ]
    non_write_calls = [
        tool_call for tool_call in tool_calls if not _is_proposal_tool_name(tool_call.get("name"))
    ]

    if non_write_calls:
        candidate_calls = non_write_calls
    else:
        candidate_calls = proposal_calls[:1]

    deduped_calls: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for tool_call in candidate_calls:
        identity = _tool_call_identity(tool_call)
        if identity in seen:
            continue
        seen.add(identity)
        deduped_calls.append(tool_call)

    if deduped_calls == tool_calls:
        return message

    logger.info(
        "Planner returned %s tool calls in one turn; normalized batch to %s safe call(s).",
        len(tool_calls),
        len(deduped_calls),
    )
    return message.model_copy(update={"tool_calls": deduped_calls})


def _provider_tool_spec(tool: BaseTool | Callable[..., Any]) -> Any:
    if not isinstance(tool, BaseTool):
        return tool

    schema = tool.tool_call_schema.model_json_schema()
    return convert_to_openai_tool(
        {
            "name": tool.name,
            "description": tool.description or schema.get("description") or "",
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        }
    )


@dataclass
class LangChainCopilotPlanner:
    settings: Settings

    _planner_model: ChatGoogleGenerativeAI | None = None
    _patch_model: ChatGoogleGenerativeAI | None = None

    @staticmethod
    def _provider_runtime_kwargs() -> dict[str, Any]:
        # Google AFC (Automatic Function Calling) would re-enter its own tool loop
        # server-side, bypassing our LangGraph state machine. That means tool results
        # would never reach our state reducers, streaming events would be missing, and
        # our per-turn budgets (max_iterations, max_patch_operations) would not apply.
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
        runnable = self._planner_model_instance().bind_tools(
            [_provider_tool_spec(tool) for tool in tools]
        )
        
        current_messages = list(messages)
        for attempt in range(1, 4):
            response = self._invoke_with_retry(
                "planner tool calling",
                lambda curr_msgs=list(current_messages): runnable.invoke(
                    [
                        SystemMessage(content=self._planner_system_instruction()),
                        HumanMessage(content=render_turn_context(state)),
                        *curr_msgs,
                    ],
                    **self._provider_runtime_kwargs(),
                ),
            )
            if not isinstance(response, AIMessage):
                raise RuntimeError("Planner did not return an AIMessage")
                
            has_tools = bool(response.tool_calls)
            has_text = bool(response.content.strip()) if isinstance(response.content, str) else bool(response.content)
            
            if has_tools or has_text:
                return _filter_parallel_tool_calls(response)
                
            # Gemini occasionally returns an empty AIMessage (no text, no tool calls)
            # on complex tool schemas, especially after a large tool result in context.
            # Injecting an explicit error forces it to generate a non-empty turn.
            logger.warning("El planner devolvio una respuesta vacia en el intento %d. Forzando reintento.", attempt)
            current_messages.extend([
                response,
                HumanMessage(content=(
                    "Tu ultima respuesta estuvo completamente vacia (sin texto ni tools). "
                    "Esto es un ERROR. Por favor, usa una tool para continuar el flujo de edicion "
                    "o responde con un mensaje de texto explicando por que te detuviste."
                ))
            ])
            
        logger.error("El planner fallo 3 veces devolviendo respuestas vacias repetidamente.")
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
        requested_tool_instruction: str | None = None,
    ) -> DraftedPatchPlan:
        messages = [
            SystemMessage(
                content=self._patch_system_instruction(
                    requested_tool_name=requested_tool_name,
                )
            ),
            HumanMessage(
                content=render_patch_input(
                    state=state,
                    target_document=target_document,
                    target_document_content=target_document_content,
                    supporting_context=supporting_context,
                    span_payload=span_payload,
                    requested_tool_name=requested_tool_name,
                    requested_tool_instruction=requested_tool_instruction,
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
        # json_schema forces the model to return a typed DraftedPatchPlan in one shot.
        # function_calling was tried and dropped: it caused Gemini to echo tool names
        # (propose_replace_span) as operation_type values instead of the patch enum
        # constants (replace_span), and re-introduced AFC-like multi-turn behavior
        # that bypassed our structured output contract.
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
                attempts=2,
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
                # 1400 tokens permiten al planner generar resúmenes clínicos completos
                # cuando action_type='respond' (ej. resumir una nota de 11 secciones).
                # 700 era suficiente para routing y tool calls cortos pero cortaba
                # respuestas textuales largas sin ningún error explícito.
                max_tokens=1400,
            )
        return self._planner_model

    def _patch_model_instance(self) -> ChatGoogleGenerativeAI:
        if self._patch_model is None:
            self._patch_model = self._build_chat_model(
                temperature=0.0,
                # 3200 tokens para dar espacio al drafter cuando emite 5-8 patches en un solo
                # structured-output call (propagation/reinterpretation). 1600 era suficiente
                # para un solo patch pero insuficiente para planes multi-sección.
                max_tokens=3200,
            )
        return self._patch_model

    def _build_chat_model(
        self,
        *,
        temperature: float,
        max_tokens: int,
    ) -> ChatGoogleGenerativeAI:
        # planner.py stays as a thin facade over app/llm/ so runtime behavior remains
        # stable while prompt/render helpers become easier to reason about and test.
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
        return planner_system_instruction()

    @staticmethod
    def _patch_system_instruction(*, requested_tool_name: str | None) -> str:
        return patch_system_instruction(requested_tool_name=requested_tool_name)

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
