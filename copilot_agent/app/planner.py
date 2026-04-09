from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

from google.genai import types as genai_types
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.llm.context_rendering import render_patch_input, render_turn_context
from app.llm.instructions import patch_system_instruction, planner_system_instruction
from app.llm.providers import (
    LlmProviderSpec,
    build_langchain_chat_model,
    resolve_runtime_provider_specs,
)

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
            "'cosmetic' = ajuste de estilo, formato o redaccion sin cambio de datos ni "
            "significado clinico. El alcance del cambio lo decide edit_scope: un reformateo "
            "amplio puede seguir siendo propagation aunque el impacto sea cosmetic. "
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
    content_preview: str
    rationale: str = Field(
        default="",
        description=(
            "Short clinical rationale for the patch. Leave empty only if the model "
            "cannot provide a concise rationale safely."
        ),
    )
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

    _planner_model: Any | None = None
    _patch_model: Any | None = None

    @staticmethod
    def _is_google_chat_model(model: Any) -> bool:
        return model.__class__.__name__ == "ChatGoogleGenerativeAI"

    @staticmethod
    def _is_openai_chat_model(model: Any) -> bool:
        return model.__class__.__name__ == "ChatOpenAI"

    @classmethod
    def _provider_runtime_kwargs_for_model(cls, model: Any) -> dict[str, Any]:
        # Google AFC (Automatic Function Calling) would re-enter its own tool loop
        # server-side, bypassing our LangGraph state machine. That means tool results
        # would never reach our state reducers, streaming events would be missing, and
        # our per-turn budgets (max_iterations, max_patch_operations) would not apply.
        if cls._is_google_chat_model(model):
            return {
                "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(
                    disable=True
                )
            }

        # OpenAI enables parallel tool calls by default. The clinical planner relies on
        # a single ordered tool decision per turn so evals stay comparable to the
        # LangGraph runtime, where writes and reads are budgeted sequentially.
        if cls._is_openai_chat_model(model):
            return {"parallel_tool_calls": False}

        return {}

    @staticmethod
    def _planner_provider_spec(settings: Settings) -> LlmProviderSpec:
        planner_spec, _ = resolve_runtime_provider_specs(settings)
        return planner_spec

    @staticmethod
    def _patch_provider_spec(settings: Settings) -> LlmProviderSpec:
        _, patch_spec = resolve_runtime_provider_specs(settings)
        return patch_spec

    @staticmethod
    def _langsmith_trace_config(
        *,
        role: Literal["planner", "drafter"],
        operation: str,
        provider_spec: LlmProviderSpec,
        iteration: int | None = None,
        tool_names: list[str] | None = None,
    ) -> dict[str, Any]:
        # Build a human-readable run_name so LangSmith traces show which component
        # is running, at which iteration, and what tools it called. Instead of seeing
        # six identical "Planner" spans, you see:
        #   Planner [i=2] → read_document, set_edit_plan
        #   Drafter [i=2] → structured_output
        role_label = "Planner" if role == "planner" else "Drafter"
        name_parts = [role_label]
        if iteration is not None:
            name_parts.append(f"[i={iteration}]")
        if tool_names:
            name_parts.append("→ " + ", ".join(tool_names))
        elif role == "drafter":
            name_parts.append("→ structured_output")
        run_name = " ".join(name_parts)

        metadata = {
            "component": "copilot_agent",
            "llm_role": role,
            "llm_operation": operation,
            "provider_family": provider_spec.provider_family,
            "model_name": provider_spec.model_name,
        }
        if iteration is not None:
            metadata["iteration"] = iteration
        if provider_spec.google_location:
            metadata["google_location"] = provider_spec.google_location
        return {
            "run_name": run_name,
            "tags": [
                "copilot_agent",
                "llm",
                role,
                operation,
                provider_spec.provider_family,
            ],
            "metadata": metadata,
        }

    @classmethod
    def _configure_runnable_for_trace(
        cls,
        runnable: Any,
        *,
        role: Literal["planner", "drafter"],
        operation: str,
        provider_spec: LlmProviderSpec,
        iteration: int | None = None,
        tool_names: list[str] | None = None,
    ) -> Any:
        with_config = getattr(runnable, "with_config", None)
        if not callable(with_config):
            return runnable
        return with_config(
            cls._langsmith_trace_config(
                role=role,
                operation=operation,
                provider_spec=provider_spec,
                iteration=iteration,
                tool_names=tool_names,
            )
        )

    def invoke_model(
        self,
        *,
        state: Mapping[str, Any],
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool | Callable[..., Any]],
    ) -> AIMessage:
        planner_model = self._planner_model_instance()
        planner_spec = self._planner_provider_spec(self.settings)
        planner_runtime_kwargs = self._provider_runtime_kwargs_for_model(planner_model)
        runnable = planner_model.bind_tools(
            [_provider_tool_spec(tool) for tool in tools]
        )
        # iteration_count in state reflects the count BEFORE this turn increments it,
        # so the upcoming planner call is iteration+1.
        current_iteration = int(state.get("iteration_count") or 0) + 1
        # Derive the tool names the planner called in the PREVIOUS turn so the
        # trace label reflects what action triggered this invocation (e.g. after
        # read_document the next span shows "Planner [i=2] → set_edit_plan").
        prev_tool_calls: list[str] = [
            str(tc.get("tool_name") or tc.get("name") or "")
            for tc in (state.get("tool_calls") or [])
            if tc.get("tool_name") or tc.get("name")
        ]
        runnable = self._configure_runnable_for_trace(
            runnable,
            role="planner",
            operation="tool_calling",
            provider_spec=planner_spec,
            iteration=current_iteration,
            tool_names=prev_tool_calls or None,
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
                    **planner_runtime_kwargs,
                ),
            )
            if not isinstance(response, AIMessage):
                raise RuntimeError("Planner did not return an AIMessage")
                
            has_tools = bool(response.tool_calls)
            has_text = bool(response.content.strip()) if isinstance(response.content, str) else bool(response.content)
            
            if has_tools or has_text:
                return _filter_parallel_tool_calls(response)
                
            # Gemini occasionally returns an empty AIMessage (no text, no tool calls)
            # on complex tool schemas, especially after a large tool result in context
            # (e.g. a full read_document payload adds ~1000 tokens to context).
            # Do NOT append the empty AIMessage — an AIMessage with no content and no
            # tool_calls is an invalid conversation turn and confuses the model on
            # subsequent retries. Only inject a directive HumanMessage.
            logger.warning("El planner devolvio una respuesta vacia en el intento %d. Forzando reintento.", attempt)
            current_messages.append(
                HumanMessage(content=self._empty_response_recovery_prompt(state))
            )
            
        logger.error("El planner fallo 3 veces devolviendo respuestas vacias repetidamente.")
        return self._empty_response_fallback_message(state)

    @staticmethod
    def _last_error_is_drafter_failure(state: Mapping[str, Any]) -> bool:
        """Detect whether the last tool error was a drafter/patch invocation failure.

        When the drafter fails (e.g. json_schema parsing, RESOURCE_EXHAUSTED),
        re-proposing the same propose_* call will just loop into another drafter
        failure.  The recovery prompt and fallback must NOT suggest propose_* again.
        """
        error = str(state.get("last_tool_error") or "").lower()
        if not error:
            return False
        drafter_markers = (
            "patch clinico",
            "patch drafting",
            "json_schema",
            "draftedpatchplan",
            "recurso de ia agotado",
        )
        return any(marker in error for marker in drafter_markers)

    @staticmethod
    def _build_scoped_instruction(state: Mapping[str, Any]) -> str:
        user_query = str(state.get("user_message") or "").strip()
        clinical_plan = state.get("clinical_plan") or {}
        affected_sections = [
            str(section).strip()
            for section in (clinical_plan.get("affected_sections") or [])
            if str(section).strip()
        ]
        reasoning = str(clinical_plan.get("reasoning") or "").strip()

        if not affected_sections:
            return user_query or "Materializa el cambio pedido usando el documento leido."

        sections_label = ", ".join(affected_sections)
        parts = [
            f"Aplica el cambio solo dentro de estas secciones: {sections_label}.",
        ]
        if user_query:
            parts.append(f"Pedido actual del medico: {user_query}.")
        if reasoning:
            parts.append(f"Contexto clinico relevante heredado del planner: {reasoning}.")
        parts.append(
            "No toques otras secciones del documento aunque contengan texto parecido."
        )
        return " ".join(parts)

    @staticmethod
    def _empty_response_recovery_prompt(state: Mapping[str, Any]) -> str:
        # Build a directive recovery message based on what the planner already has
        # in state. A generic "you were empty, try again" often makes things worse
        # because the model receives an empty AIMessage + a vague error and loops.
        # A state-aware prompt points the model to its concrete next action.
        #
        # IMPORTANT: if the last tool error indicates a drafter failure, we must NOT
        # suggest propose_* again — that would create an infinite loop where the
        # drafter keeps failing and the planner keeps re-proposing.
        read_docs = state.get("read_documents") or []
        clinical_plan = state.get("clinical_plan") or {}
        next_required_action = str(state.get("next_required_action") or "").strip()
        read_ids = [d.get("document_id") for d in read_docs if d.get("document_id")]

        parts = [
            "Tu respuesta anterior estuvo completamente vacia (sin texto ni tool calls). "
            "No devuelvas una respuesta vacia. Debes continuar el flujo."
        ]

        fallback_target_document_id = LangChainCopilotPlanner._fallback_target_document_id(
            state
        )
        user_query = str(state.get("user_message") or "").strip()
        scoped_instruction = LangChainCopilotPlanner._build_scoped_instruction(state)
        drafter_just_failed = LangChainCopilotPlanner._last_error_is_drafter_failure(state)

        if drafter_just_failed:
            # The drafter crashed (json parse, 429, etc.) — re-proposing will loop.
            # Tell the planner to surface the failure as a user-facing text response
            # instead of calling propose_* again.
            parts.append(
                "La tool propose_* acaba de fallar al redactar el patch clinico. "
                "NO vuelvas a llamar propose_*. Responde con un mensaje de texto breve "
                "explicando al medico que no pudiste materializar la edicion en este "
                "momento y que puede intentar de nuevo."
            )
        elif fallback_target_document_id and (
            clinical_plan.get("edit_scope")
            or LangChainCopilotPlanner._looks_like_edit_request(user_query)
        ):
            # After a successful full read, the most common empty-response failure mode
            # is that Gemini stalls deciding whether to propose or ask for clarification.
            # Tell it explicitly to stop reading and open exactly one proposal tool call.
            parts.append(
                f"No vuelvas a leer. Ya tienes suficiente contexto del documento {fallback_target_document_id}. "
                f"Tu siguiente paso obligatorio es llamar EXACTAMENTE una sola tool propose_* "
                f"para ese documento. Si no estas seguro del tipo exacto, usa "
                f"propose_replace_span(target_document_id='{fallback_target_document_id}', "
                f"instruction='{scoped_instruction}')."
            )
        elif clinical_plan.get("edit_scope") and read_ids:
            # Planner has a plan and already read the document — next step is propose
            parts.append(
                f"Ya tienes un plan clinico (scope={clinical_plan['edit_scope']}) "
                f"y leiste los documentos: {', '.join(read_ids)}. "
                f"Tu siguiente paso obligatorio es llamar propose_replace_span("
                f"target_document_id='{read_ids[-1]}', "
                f"instruction='{scoped_instruction}') "
                f"consolidando todos los cambios en UNA sola llamada."
            )
        elif next_required_action == "draft_patch_set":
            parts.append(
                "Ya existe un edit_plan pendiente en el runtime. "
                "No vuelvas a clasificar el scope. "
                "Si falta la nota completa, tu siguiente paso es leerla con read_document(mode='full'). "
                "Si la nota completa ya esta disponible, tu siguiente paso es proponer patches."
            )
        elif read_ids:
            parts.append(
                f"Ya leiste los documentos: {', '.join(read_ids)}. "
                "Usa esa informacion para proponer cambios con propose_* "
                "o responde al medico con texto explicando tu analisis."
            )
        else:
            parts.append(
                "Usa una tool para avanzar o responde con un mensaje de texto "
                "explicando tu analisis o por que no puedes continuar."
            )

        return " ".join(parts)

    @staticmethod
    def _looks_like_edit_request(user_query: str) -> bool:
        normalized = str(user_query or "").strip().lower()
        if not normalized:
            return False
        edit_markers = (
            "agrega",
            "agrega",
            "añade",
            "anade",
            "inserta",
            "cambia",
            "modifica",
            "actualiza",
            "corrige",
            "reemplaza",
            "elimina",
            "borra",
            "quita",
            "reescribe",
            "redacta",
            "propaga",
            "ajusta",
            "completa",
        )
        return any(marker in normalized for marker in edit_markers)

    @staticmethod
    def _fallback_target_document_id(state: Mapping[str, Any]) -> str | None:
        full_read_ids: list[str] = []
        seen_full_read_ids: set[str] = set()
        for document in state.get("read_documents") or []:
            read_mode = str(document.get("read_mode") or document.get("mode") or "")
            document_id = str(document.get("document_id") or "")
            if read_mode != "full" or not document_id or document_id in seen_full_read_ids:
                continue
            seen_full_read_ids.add(document_id)
            full_read_ids.append(document_id)

        if len(full_read_ids) == 1:
            return full_read_ids[0]

        read_ids: list[str] = []
        seen_read_ids: set[str] = set()
        for document in state.get("read_documents") or []:
            document_id = str(document.get("document_id") or "")
            if not document_id or document_id in seen_read_ids:
                continue
            seen_read_ids.add(document_id)
            read_ids.append(document_id)
        if len(read_ids) == 1:
            return read_ids[0]
        return None

    @staticmethod
    def _empty_response_fallback_message(state: Mapping[str, Any]) -> AIMessage:
        target_document_id = LangChainCopilotPlanner._fallback_target_document_id(state)
        clinical_plan = state.get("clinical_plan") or {}
        scoped_instruction = LangChainCopilotPlanner._build_scoped_instruction(state)
        drafter_just_failed = LangChainCopilotPlanner._last_error_is_drafter_failure(state)
        scoped_sections = list(clinical_plan.get("affected_sections") or [])

        # If the drafter just crashed (json parse error, 429, etc.), re-proposing
        # will enter the exact same failure path and loop.  Surface a safe text
        # response so the run finishes cleanly instead of cycling.
        if drafter_just_failed:
            logger.warning(
                "Planner vacio 3 veces tras fallo del drafter; devolviendo error textual "
                "en lugar de re-proponer para evitar loop."
            )
            return AIMessage(
                content=(
                    "No pude materializar la edicion solicitada porque el servicio de IA "
                    "no logro generar un borrador valido. "
                    "Por favor, intenta de nuevo o reformula la instruccion."
                )
            )

        # Safety rationale: once the provider has returned an empty planner turn 3 times,
        # hard-failing the run is worse than forcing a single propose_* call when we have
        # one clearly-read target document and an edit-like user request. This fallback
        # does NOT write canonically; it only opens the normal propose_* path, which still
        # goes through patch drafting, validation, backend conflict checks and human review.
        if target_document_id and (
            clinical_plan.get("edit_scope")
            or LangChainCopilotPlanner._looks_like_edit_request(user_query)
        ):
            logger.warning(
                "Planner quedo vacio 3 veces; sintetizando propose_replace_span fallback para %s.",
                target_document_id,
            )
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_replace_span",
                        "args": {
                            "target_document_id": target_document_id,
                            "instruction": scoped_instruction,
                            "affected_sections": scoped_sections or None,
                        },
                        "id": f"empty-response-fallback-{uuid.uuid4()}",
                        "type": "tool_call",
                    }
                ],
            )

        logger.warning(
            "Planner quedo vacio 3 veces sin target de edicion claro; devolviendo respuesta textual segura."
        )
        return AIMessage(
            content=(
                "Lei el documento disponible, pero no pude decidir automaticamente el siguiente paso. "
                "Indica el cambio exacto que deseas realizar o vuelve a intentarlo."
            )
        )

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
        requested_affected_sections: Sequence[str] | None = None,
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
                    requested_affected_sections=requested_affected_sections,
                )
            ),
        ]
        result = self._invoke_patch_drafting(messages=messages, state=state)
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
        state: Mapping[str, Any] | None = None,
    ) -> Any:
        # json_schema forces the model to return a typed DraftedPatchPlan in one shot.
        # function_calling was tried and dropped: it caused Gemini to echo tool names
        # (propose_replace_span) as operation_type values instead of the patch enum
        # constants (replace_span), and re-introduced AFC-like multi-turn behavior
        # that bypassed our structured output contract.
        patch_model = self._patch_model_instance()
        patch_spec = self._patch_provider_spec(self.settings)
        structured = self._patch_structured_output_runnable(
            patch_model,
            provider_spec=patch_spec,
        )
        # Pass iteration from state so the drafter span shows which planner
        # iteration triggered the drafting call (e.g. "Drafter [i=3]").
        drafter_iteration = int((state or {}).get("iteration_count") or 0) + 1
        structured = self._configure_runnable_for_trace(
            structured,
            role="drafter",
            operation="structured_output",
            provider_spec=patch_spec,
            iteration=drafter_iteration,
        )
        # Do NOT pass _provider_runtime_kwargs_for_model here: those kwargs
        # (parallel_tool_calls for OpenAI, AFC disable for Gemini) only apply
        # when tools are bound. Structured output via json_schema has no tools,
        # and OpenAI rejects parallel_tool_calls without a tools list.
        try:
            return self._invoke_with_retry(
                "patch drafting via json_schema",
                lambda: structured.invoke(
                    messages,
                ),
                attempts=2,
            )
        except Exception as error:  # pragma: no cover - provider edge
            raise RuntimeError(
                "patch drafting failed with json_schema structured output: "
                f"{error}"
            ) from error

    def _patch_structured_output_runnable(
        self,
        model: Any,
        *,
        provider_spec: LlmProviderSpec,
    ) -> Any:
        # Gemini's native json_schema mode is the most reliable path for our writer
        # flow. For other LangChain adapters we keep the same DraftedPatchPlan schema
        # but let each provider choose its supported structured-output transport.
        if provider_spec.provider_family == "google" or self._is_google_chat_model(model):
            return model.with_structured_output(DraftedPatchPlan, method="json_schema")
        return model.with_structured_output(DraftedPatchPlan)

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

    def _planner_model_instance(self) -> Any:
        if self._planner_model is None:
            planner_spec = self._planner_provider_spec(self.settings)
            self._planner_model = build_langchain_chat_model(
                settings=self.settings,
                provider_spec=planner_spec,
                temperature=0.1,
                # 1400 tokens permiten al planner generar resúmenes clínicos completos
                # cuando action_type='respond' (ej. resumir una nota de 11 secciones).
                # 700 era suficiente para routing y tool calls cortos pero cortaba
                # respuestas textuales largas sin ningún error explícito.
                max_tokens=1400,
            )
        return self._planner_model

    def _patch_model_instance(self) -> Any:
        if self._patch_model is None:
            patch_spec = self._patch_provider_spec(self.settings)
            self._patch_model = build_langchain_chat_model(
                settings=self.settings,
                provider_spec=patch_spec,
                temperature=0.0,
                # 3200 tokens para dar espacio al drafter cuando emite 5-8 patches en un solo
                # structured-output call (propagation/reinterpretation). 1600 era suficiente
                # para un solo patch pero insuficiente para planes multi-sección.
                max_tokens=3200,
            )
        return self._patch_model

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
            patches.append(
                patch.model_copy(
                    update={
                        "content_preview": patch.content_preview or "",
                    }
                )
            )
        document_preview_after = result.document_preview_after
        if not document_preview_after and patches:
            document_preview_after = patches[-1].content_preview or None
        return DraftedPatchPlan(
            patches=patches,
            rationale=result.rationale,
            document_preview_after=document_preview_after,
        )


def build_planner(settings: Settings) -> CopilotPlanner:
    return LangChainCopilotPlanner(settings=settings)
