from __future__ import annotations

import pytest

from common.templates import load_template
from context_pipeline.classify_clusters.lib import parse_classify_clusters_result


def test_parse_classify_clusters_result() -> None:
    raw = '{"assignments": {"c1": ["antecedentes"]}}'
    result = parse_classify_clusters_result(raw)
    assert result.assignments["c1"] == ["antecedentes"]


def test_audit_classify_unknown_cluster() -> None:
    from common.context_spans import (
        ClassifyClustersResult,
        SpanCluster,
        audit_classify_clusters,
    )

    template = load_template("minimal_outpatient_v001")
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    result = ClassifyClustersResult(assignments={"c9": ["antecedentes"]})
    with pytest.raises(ValueError, match="unknown_cluster_id"):
        audit_classify_clusters(clusters, template, result)
