from __future__ import annotations

import pytest

from common.context_spans import DoctorItem
from context_pipeline.triage.lib import parse_triage_result, render_triage_payload
from context_pipeline.triage.prompts.triage_prompt_v001 import SYSTEM_PROMPT


def test_parse_triage_result_accepts_numeric_ids() -> None:
    raw = """
    {
      "directives": [
        {
          "scope": "document",
          "action": "limit_source_to",
          "target": "case2_epicrisis",
          "topic": "neumonía"
        }
      ],
      "content_ids": [3],
      "drop_ids": [1]
    }
    """
    result = parse_triage_result(raw)
    assert result.content_ids == ["3"]
    assert result.drop_ids == ["1"]


def test_parse_triage_result_rejects_unknown_item_id() -> None:
    from common.context_spans import TriageResult, audit_triage_result

    result = TriageResult(content_ids=["9"], drop_ids=[])
    items = [DoctorItem(id="1", text="x")]
    with pytest.raises(ValueError, match="unknown_item_id"):
        audit_triage_result(items, result)


def test_render_triage_payload_v001_uses_input_json_block() -> None:
    items = [
        DoctorItem(id="1", text="Paciente alérgico a penicilina."),
        DoctorItem(id="2", text="Usar laboratorios."),
    ]
    payload = render_triage_payload(
        session_id="s1",
        items=items,
        prompt_version="v001",
    )
    assert payload.startswith("Ahora procesa el siguiente caso.")
    assert "<input_json>" in payload
    assert '"id": 1' in payload
    assert '"id": 2' in payload
    assert "Paciente alérgico a penicilina." in payload


def test_triage_prompt_v001_system_identity() -> None:
    assert "doctor_context_triage" in SYSTEM_PROMPT
    assert "content_ids" in SYSTEM_PROMPT
