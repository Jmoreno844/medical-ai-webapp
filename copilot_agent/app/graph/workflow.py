from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.graph.nodes import (
    NODE_APPLY_PATCH_REVIEW,
    NODE_DRAFT_PATCH_FROM_PLAN,
    NODE_EXECUTE_TOOLS,
    NODE_FINALIZE_RUN,
    NODE_PLANNER_TURN,
    NODE_RECONCILE_TOOL_STATE,
    NODE_WAIT_FOR_HUMAN_REVIEW,
    apply_patch_review,
    finalize_run,
    make_draft_patch_from_plan_node,
    make_planner_turn_node,
    reconcile_tool_state,
    route_after_planner_turn,
    route_after_tool_execution,
    wait_for_human_review,
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

    graph.add_node(NODE_PLANNER_TURN, make_planner_turn_node(planner, tools))
    graph.add_node(NODE_DRAFT_PATCH_FROM_PLAN, make_draft_patch_from_plan_node(planner))
    graph.add_node(
        NODE_EXECUTE_TOOLS,
        ToolNode(
            tools,
            handle_tool_errors=_tool_error_message,
        ),
    )
    graph.add_node(NODE_RECONCILE_TOOL_STATE, reconcile_tool_state)
    graph.add_node(NODE_WAIT_FOR_HUMAN_REVIEW, wait_for_human_review)
    graph.add_node(NODE_APPLY_PATCH_REVIEW, apply_patch_review)
    graph.add_node(NODE_FINALIZE_RUN, finalize_run)

    graph.set_entry_point(NODE_PLANNER_TURN)
    graph.add_conditional_edges(
        NODE_PLANNER_TURN,
        route_after_planner_turn,
        {
            NODE_DRAFT_PATCH_FROM_PLAN: NODE_DRAFT_PATCH_FROM_PLAN,
            NODE_EXECUTE_TOOLS: NODE_EXECUTE_TOOLS,
            NODE_WAIT_FOR_HUMAN_REVIEW: NODE_WAIT_FOR_HUMAN_REVIEW,
            NODE_FINALIZE_RUN: NODE_FINALIZE_RUN,
        },
    )
    graph.add_edge(NODE_EXECUTE_TOOLS, NODE_RECONCILE_TOOL_STATE)
    graph.add_conditional_edges(
        NODE_RECONCILE_TOOL_STATE,
        route_after_tool_execution,
        {
            NODE_DRAFT_PATCH_FROM_PLAN: NODE_DRAFT_PATCH_FROM_PLAN,
            NODE_PLANNER_TURN: NODE_PLANNER_TURN,
            NODE_WAIT_FOR_HUMAN_REVIEW: NODE_WAIT_FOR_HUMAN_REVIEW,
            NODE_FINALIZE_RUN: NODE_FINALIZE_RUN,
        },
    )
    graph.add_conditional_edges(
        NODE_DRAFT_PATCH_FROM_PLAN,
        route_after_tool_execution,
        {
            NODE_DRAFT_PATCH_FROM_PLAN: NODE_DRAFT_PATCH_FROM_PLAN,
            NODE_PLANNER_TURN: NODE_PLANNER_TURN,
            NODE_WAIT_FOR_HUMAN_REVIEW: NODE_WAIT_FOR_HUMAN_REVIEW,
            NODE_FINALIZE_RUN: NODE_FINALIZE_RUN,
        },
    )
    graph.add_conditional_edges(
        NODE_WAIT_FOR_HUMAN_REVIEW,
        lambda state: NODE_APPLY_PATCH_REVIEW
        if state.get("review_result") == "approve"
        else NODE_FINALIZE_RUN,
        {
            NODE_APPLY_PATCH_REVIEW: NODE_APPLY_PATCH_REVIEW,
            NODE_FINALIZE_RUN: NODE_FINALIZE_RUN,
        },
    )
    graph.add_edge(NODE_APPLY_PATCH_REVIEW, NODE_FINALIZE_RUN)
    graph.add_edge(NODE_FINALIZE_RUN, END)

    return graph.compile(checkpointer=checkpointer)
