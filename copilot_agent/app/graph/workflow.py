from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.graph.nodes import (
    _route_after_model,
    _route_after_tools,
    apply_patch,
    consolidate_tool_state,
    finalize_response,
    interrupt_for_review,
    make_call_model_node,
)
from app.graph.state import CopilotState
from app.graph.tools import build_graph_tools


def _tool_error_message(error: Exception) -> str:
    return (
        "La llamada de tool fallo por un problema corregible. "
        f"Detalle: {error}. Ajusta el schema o el orden de las tools y reintenta."
    )


def build_clinical_copilot_graph(*, tools_client, planner, checkpointer=None):
    graph = StateGraph(CopilotState)
    tools = build_graph_tools(
        tools_client=tools_client,
        planner=planner,
    )

    graph.add_node("call_model", make_call_model_node(planner, tools))
    graph.add_node(
        "tools",
        ToolNode(
            tools,
            handle_tool_errors=_tool_error_message,
        ),
    )
    graph.add_node("consolidate_tool_state", consolidate_tool_state)
    graph.add_node("interrupt_for_review", interrupt_for_review)
    graph.add_node("apply_patch", apply_patch)
    graph.add_node("finalize_response", finalize_response)

    graph.set_entry_point("call_model")
    graph.add_conditional_edges(
        "call_model",
        _route_after_model,
        {
            "tools": "tools",
            "interrupt_for_review": "interrupt_for_review",
            "finalize_response": "finalize_response",
        },
    )
    graph.add_edge("tools", "consolidate_tool_state")
    graph.add_conditional_edges(
        "consolidate_tool_state",
        _route_after_tools,
        {
            "call_model": "call_model",
            "interrupt_for_review": "interrupt_for_review",
            "finalize_response": "finalize_response",
        },
    )
    graph.add_conditional_edges(
        "interrupt_for_review",
        lambda state: "apply_patch"
        if state.get("review_result") == "approve"
        else "finalize_response",
        {
            "apply_patch": "apply_patch",
            "finalize_response": "finalize_response",
        },
    )
    graph.add_edge("apply_patch", "finalize_response")
    graph.add_edge("finalize_response", END)

    return graph.compile(checkpointer=checkpointer)
