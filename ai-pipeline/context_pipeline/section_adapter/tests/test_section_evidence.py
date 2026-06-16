from __future__ import annotations

from common.context_spans import Span, SpanCluster, SpanKind, build_section_evidence


def test_build_section_evidence_collects_spans_per_section() -> None:
    spans_by_id = {
        "1": Span(id="1", doc="epicrisis", kind=SpanKind.LINE, text="HTA."),
        "2": Span(id="2", doc="lab", kind=SpanKind.LINE, text="Hb 12."),
    }
    clusters_by_id = {
        "c1": SpanCluster(id="c1", span_ids=["1"]),
        "c2": SpanCluster(id="c2", span_ids=["2"]),
    }
    adapter_jobs = {
        "antecedentes": ["c1"],
        "estudios_y_resultados": ["c2"],
    }
    evidence = build_section_evidence(adapter_jobs, clusters_by_id, spans_by_id)
    assert evidence["antecedentes"][0]["id"] == "1"
    assert evidence["estudios_y_resultados"][0]["doc"] == "lab"
    assert "text" in evidence["antecedentes"][0]
