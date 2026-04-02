from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    apply_patch,
    accumulate_observation,
    finalize_response,
    interrupt_for_review,
    make_call_tool_node,
    make_plan_or_next_action_node,
)
from app.graph.state import CopilotState


def build_clinical_copilot_graph(*, tools_client, planner, checkpointer=None):
    graph = StateGraph(CopilotState)

    plan_or_next_action = make_plan_or_next_action_node(planner)
    call_tool = make_call_tool_node(tools_client, planner)

    graph.add_node("plan_or_next_action", plan_or_next_action)
    graph.add_node("call_tool", call_tool)
    graph.add_node("accumulate_observation", accumulate_observation)
    graph.add_node("interrupt_for_review", interrupt_for_review)
    graph.add_node("apply_patch", apply_patch)
    graph.add_node("finalize_response", finalize_response)

    graph.set_entry_point("plan_or_next_action")
    graph.add_conditional_edges(
        "plan_or_next_action",
        lambda state: "call_tool"
        if (state.get("pending_action") or {}).get("action_type") == "call_tool"
        else "interrupt_for_review"
        if state.get("requires_human_review") and state.get("patch_preview")
        else "finalize_response",
        {
            "call_tool": "call_tool",
            "finalize_response": "finalize_response",
            "interrupt_for_review": "interrupt_for_review",
        },
    )
    graph.add_edge("call_tool", "accumulate_observation")
    graph.add_conditional_edges(
        "accumulate_observation",
        lambda state: "interrupt_for_review"
        if state.get("requires_human_review") and state.get("patch_preview")
        else "finalize_response"
        if state.get("final_response")
        else "plan_or_next_action",
        {
            "plan_or_next_action": "plan_or_next_action",
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
