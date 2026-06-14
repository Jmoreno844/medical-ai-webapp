from __future__ import annotations

import pytest

from common.context_spans import DoctorItem
from context_pipeline.triage.lib import parse_triage_result


def test_parse_triage_result() -> None:
    raw = """
    {
      "directives": [{"target": "epicrisis", "action": "limit_to"}],
      "content_ids": ["m3"],
      "drop_ids": ["m1"]
    }
    """
    result = parse_triage_result(raw)
    assert result.content_ids == ["m3"]
    assert result.drop_ids == ["m1"]


def test_parse_triage_result_rejects_unknown_item_id() -> None:
    from common.context_spans import TriageResult, audit_triage_result

    result = TriageResult(content_ids=["m9"], drop_ids=[])
    items = [DoctorItem(id="m1", text="x")]
    with pytest.raises(ValueError, match="unknown_item_id"):
        audit_triage_result(items, result)
