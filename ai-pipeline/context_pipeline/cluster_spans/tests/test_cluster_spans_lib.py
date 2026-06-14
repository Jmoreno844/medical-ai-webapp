from __future__ import annotations

from context_pipeline.cluster_spans.lib import parse_cluster_spans_result


def test_parse_cluster_spans_result() -> None:
    raw = '{"clusters": [{"id": "c1", "span_ids": ["s1", "s2"]}]}'
    clusters = parse_cluster_spans_result(raw)
    assert len(clusters) == 1
    assert clusters[0].id == "c1"
