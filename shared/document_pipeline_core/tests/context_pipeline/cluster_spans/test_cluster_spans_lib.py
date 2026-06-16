from __future__ import annotations

import json

from document_pipeline_core.common.context_spans import Span, SpanKind
from document_pipeline_core.context_pipeline.cluster_spans.lib import (
    cluster_spans_prompt_reference,
    parse_cluster_spans_result,
    render_cluster_spans_payload,
)


def test_parse_cluster_spans_result() -> None:
    raw = '{"clusters": [{"id": "c1", "span_ids": ["s1", "s2"]}]}'
    clusters = parse_cluster_spans_result(raw)
    assert len(clusters) == 1
    assert clusters[0].id == "c1"


def test_render_cluster_spans_payload_v001_json() -> None:
    spans = [
        Span(
            id="s1",
            doc="doc",
            kind=SpanKind.LINE,
            text="marzo de 2024",
            date_hint="marzo de 2024",
        )
    ]
    payload = json.loads(render_cluster_spans_payload(spans=spans, prompt_version="v001"))
    serialized = json.dumps(payload)
    assert "date_hint" not in serialized
    assert "date_hints" not in serialized


def test_render_cluster_spans_payload_v002_semantic_blocks() -> None:
    spans = [
        Span(
            id="s1",
            doc="doc",
            kind=SpanKind.LINE,
            text="marzo de 2024",
            date_hint="marzo de 2024",
        )
    ]
    payload = render_cluster_spans_payload(spans=spans, prompt_version="v002")
    assert payload.startswith("<spans>")
    assert '<span id="s1" date_hints="marzo de 2024">' in payload
    assert "marzo de 2024" in payload
    assert "date_hint:" not in payload
    assert '"doc"' not in payload


def test_cluster_spans_prompt_reference_v002_points_to_py_module() -> None:
    assert cluster_spans_prompt_reference("v002").endswith(
        "context_pipeline/cluster_spans/prompts/cluster_spans_prompt_v001.py"
    )
