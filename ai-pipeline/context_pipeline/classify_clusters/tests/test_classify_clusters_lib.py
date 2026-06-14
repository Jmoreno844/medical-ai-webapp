from __future__ import annotations

import json

import pytest

from common.context_spans import Span, SpanCluster, SpanKind
from common.templates import load_template
from context_pipeline.classify_clusters.lib import (
    classify_clusters_output_schema,
    classify_clusters_prompt_reference,
    load_classify_clusters_prompt,
    parse_classify_clusters_result,
    render_classify_clusters_payload,
)


def test_parse_classify_clusters_result_list_format() -> None:
    raw = '{"assignments": [{"cluster_id": "c1", "section_ids": ["antecedentes"]}]}'
    result = parse_classify_clusters_result(raw)
    assert result.assignments[0].cluster_id == "c1"
    assert result.assignments[0].section_ids == ["antecedentes"]


def test_parse_classify_clusters_result_legacy_dict_format() -> None:
    raw = '{"assignments": {"c1": ["antecedentes"]}}'
    result = parse_classify_clusters_result(raw)
    assert result.assignments[0].cluster_id == "c1"
    assert result.assignments[0].section_ids == ["antecedentes"]


def test_parse_classify_clusters_result_empty_section_ids() -> None:
    raw = '{"assignments": [{"cluster_id": "c1", "section_ids": []}]}'
    result = parse_classify_clusters_result(raw)
    assert result.dropped_cluster_ids() == ["c1"]


def test_audit_classify_unknown_cluster() -> None:
    from common.context_spans import (
        ClassifyClustersResult,
        audit_classify_clusters,
    )

    template = load_template("minimal_outpatient_v001")
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    result = ClassifyClustersResult(
        assignments=[{"cluster_id": "c9", "section_ids": ["antecedentes"]}]
    )
    with pytest.raises(ValueError, match="unknown_cluster_id"):
        audit_classify_clusters(clusters, template, result)


def test_audit_classify_requires_complete_coverage_for_v002() -> None:
    from common.context_spans import (
        ClassifyClustersResult,
        audit_classify_clusters,
    )

    template = load_template("minimal_outpatient_v001")
    clusters = [
        SpanCluster(id="c1", span_ids=["s1"]),
        SpanCluster(id="c2", span_ids=["s2"]),
    ]
    result = ClassifyClustersResult(
        assignments=[{"cluster_id": "c1", "section_ids": ["antecedentes"]}]
    )
    with pytest.raises(ValueError, match="missing_cluster_ids"):
        audit_classify_clusters(
            clusters,
            template,
            result,
            require_complete_cluster_coverage=True,
        )


def test_render_classify_clusters_payload_includes_dates_and_cluster_hints() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [
        SpanCluster(
            id="c1",
            span_ids=["s1"],
            date_hints=["marzo de 2024"],
        )
    ]
    spans = [
        Span(
            id="s1",
            doc="epicrisis",
            kind=SpanKind.LINE,
            text="Epicrisis previa",
            date_hint="marzo de 2024",
        )
    ]
    payload = render_classify_clusters_payload(
        template=template,
        clusters=clusters,
        spans=spans,
        encounter_date="2026-06-14",
        document_date="2024-03-01",
        prompt_version="v002",
    )
    assert payload.startswith("<encounter_context>")
    assert "encounter_date: 2026-06-14" in payload
    assert "doc_date: 2024-03-01" in payload
    assert '<cluster id="c1">' in payload
    assert 'date_hints: ["marzo de 2024"]' in payload
    assert "<template_sections>" in payload
    assert "<source_spans>" in payload
    assert "Epicrisis previa" in payload
    assert "date_hint:" not in payload


def test_load_classify_clusters_prompt_v002_returns_py_system_prompt() -> None:
    from context_pipeline.classify_clusters.prompts.classify_clusters_prompt_v001 import SYSTEM_PROMPT

    assert load_classify_clusters_prompt("v002") == SYSTEM_PROMPT.strip()


def test_classify_clusters_output_schema_v002_restricts_ids() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    schema = classify_clusters_output_schema(
        template=template,
        clusters=clusters,
        prompt_version="v002",
    )
    assert schema is not None
    assignment_item = schema["properties"]["assignments"]["items"]
    assert assignment_item["properties"]["cluster_id"]["enum"] == ["c1"]


def test_classify_clusters_prompt_reference_v002_points_to_py_module() -> None:
    assert (
        classify_clusters_prompt_reference("v002")
        == "context_pipeline/classify_clusters/prompts/classify_clusters_prompt_v001.py"
    )
