from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

from google.genai import types as genai_types
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
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

    # To avoid INVALID_CONCURRENT_GRAPH_UPDATE on unannotated CopilotState lists,
    # we strictly serialize all tool calls one per turn.
    logger.info(
        "Planner returned %s tool calls in one turn; keeping only the first to avoid graph race conditions.",
        len(tool_calls),
    )
    return message.model_copy(update={"tool_calls": [tool_calls[0]]})


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
