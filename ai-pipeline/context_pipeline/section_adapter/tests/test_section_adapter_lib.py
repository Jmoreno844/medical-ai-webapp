from __future__ import annotations

import pytest

from context_pipeline.section_adapter.lib import parse_section_adapter_result


def test_parse_section_adapter_result() -> None:
    raw = '{"section_id": "antecedentes", "content": "Alergia a penicilina."}'
    result = parse_section_adapter_result(raw, expected_section_id="antecedentes")
    assert "penicilina" in result.content
