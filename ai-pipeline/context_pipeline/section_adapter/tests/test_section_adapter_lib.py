from __future__ import annotations

import json

import pytest

from common.context_spans import Span, SpanCluster, SpanKind
from common.templates import load_template
from context_pipeline.section_adapter.lib import (
    parse_section_adapter_result,
    render_section_adapter_payload,
    section_adapter_prompt_reference,
)


def test_parse_section_adapter_result_brief() -> None:
    raw = '{"section_id": "antecedentes", "brief": "Alergia a penicilina."}'
    result = parse_section_adapter_result(raw, expected_section_id="antecedentes")
    assert "penicilina" in result.brief


def test_parse_section_adapter_result_accepts_legacy_content() -> None:
    raw = '{"section_id": "antecedentes", "content": "Alergia a penicilina."}'
    result = parse_section_adapter_result(raw, expected_section_id="antecedentes")
    assert result.brief == "Alergia a penicilina."


def test_render_section_adapter_payload_v002_json() -> None:
    template = load_template("consulta_estructurada_v002")
    section = template.section_by_id("signos_vitales")
    assert section is not None
    payload = json.loads(
        render_section_adapter_payload(
            section=section,
            encounter_date=None,
            directives=[],
            clusters=[],
            spans=[],
            prompt_version="v002",
        )
    )
    assert "section_guidelines" in payload
    assert "Incluye:" in payload["section_guidelines"]


def test_render_section_adapter_payload_v003_semantic_blocks() -> None:
    template = load_template("consulta_estructurada_v002")
    section = template.section_by_id("antecedentes")
    assert section is not None
    clusters = [
        SpanCluster(
            id="c1",
            span_ids=["1"],
            date_hints=["marzo de 2024"],
        )
    ]
    spans = [
        Span(
            id="1",
            doc="epicrisis",
            kind=SpanKind.LINE,
            text="Cirugía previa",
            date_hint="marzo de 2024",
        )
    ]
    payload = render_section_adapter_payload(
        section=section,
        encounter_date="2026-06-14",
        document_date="2024-03-01",
        directives=[],
        clusters=clusters,
        spans=spans,
        prompt_version="v003",
    )
    assert payload.startswith("Ahora procesa el siguiente caso.")
    assert "<guidelines>" in payload
    assert "<input_json>" in payload
    assert "Cirugía previa" in payload
    assert "date_hint:" not in payload


def test_section_adapter_prompt_reference_v003_points_to_py_module() -> None:
    assert (
        section_adapter_prompt_reference("v003")
        == "context_pipeline/section_adapter/prompts/adapter_prompt_v001.py"
    )
