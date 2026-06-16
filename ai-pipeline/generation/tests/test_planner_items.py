from __future__ import annotations

import json

import pytest

from generation.lib import (
    PlannerItem,
    PlannerItemsResult,
    audit_planner_item_evidence,
    parse_planner_items_result,
    render_planned_items_block,
)


def test_render_planned_items_block_numbered_with_evidence() -> None:
    block = render_planned_items_block(
        [
            PlannerItem(text="Cefalea de 3 días.", e=["t0"]),
            PlannerItem(text="Sin alarma referida.", e=["t1", "t2"]),
        ]
    )
    assert block == (
        "[1] Cefalea de 3 días. evidence: t0\n"
        "[2] Sin alarma referida. evidence: t1,t2"
    )


def test_render_planned_items_block_empty() -> None:
    assert render_planned_items_block([]) == "(sin items planificados)"


def test_parse_planner_items_result_validates_evidence_ids() -> None:
    raw = json.dumps(
        {
            "items": [
                {"text": "Cefalea.", "e": ["t0"]},
            ]
        }
    )
    result = parse_planner_items_result(raw, allowed_evidence_ids={"t0"})
    assert len(result.items) == 1
    assert result.items[0].text == "Cefalea."


def test_parse_planner_items_result_rejects_unknown_evidence() -> None:
    raw = json.dumps({"items": [{"text": "Cefalea.", "e": ["s99"]}]})
    with pytest.raises(ValueError, match="unknown_evidence_id"):
        parse_planner_items_result(raw, allowed_evidence_ids={"t0"})


def test_audit_planner_item_evidence_requires_non_empty_text() -> None:
    with pytest.raises(ValueError, match="empty_item_text"):
        audit_planner_item_evidence(
            [PlannerItem(text="   ", e=["t0"])],
            allowed_evidence_ids={"t0"},
        )


def test_parse_planner_items_result_allows_empty_items() -> None:
    result = parse_planner_items_result(
        '{"items": []}',
        allowed_evidence_ids=set(),
    )
    assert result == PlannerItemsResult(items=[])
