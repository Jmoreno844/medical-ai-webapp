from __future__ import annotations

from pathlib import Path

import pytest

from document_pipeline_core.common.context_spans import (
    ClassifyClustersResult,
    DoctorItem,
    FilterSpansResult,
    SectionAdapterResult,
    Span,
    SpanCluster,
    SpanKind,
    TriageResult,
    audit_classify_clusters,
    audit_filter_spans_result,
    audit_section_adapter_result,
    audit_span_clusters,
    audit_triage_result,
    build_adapter_jobs,
    build_spans_from_pdf,
    build_spans_from_text,
    cluster_to_payload_item,
    detect_date_hint,
    doctor_items_to_spans,
    merge_spans,
    propagate_cluster_date_hints,
    split_doctor_items,
)
from document_pipeline_core.common.templates import load_template

CASE1_LAB_PDF = (
    Path(__file__).resolve().parents[2]
    / "cases"
    / "context"
    / "documents"
    / "case1_lab_anemia.pdf"
)


def test_split_doctor_items_short_note() -> None:
    items, is_pasted = split_doctor_items(
        "TA 138/88. Paciente pálido.",
        session_id="case1",
    )
    assert is_pasted is False
    assert [item.id for item in items] == ["1", "2"]
    assert items[0].text == "TA 138/88."
    assert items[1].text == "Paciente pálido."


def test_split_doctor_items_detects_pasted_by_tokens() -> None:
    long_note = " ".join(["línea clínica repetida"] * 80)
    _, is_pasted = split_doctor_items(long_note, session_id="case3")
    assert is_pasted is True


def test_doctor_items_to_spans_filters_content_ids() -> None:
    items = [
        DoctorItem(id="1", text="Alergia a penicilina."),
        DoctorItem(id="2", text="Directiva ignorar epicrisis."),
    ]
    spans = doctor_items_to_spans(items, ["1"])
    assert len(spans) == 1
    assert spans[0].doc == "nota_medico"
    assert spans[0].kind == SpanKind.LINE
    assert spans[0].text == "Alergia a penicilina."


def test_build_spans_from_text_detects_kinds() -> None:
    text = """# Laboratorio

HEMOGLOBINA | 9.2 g/dL | VR 12-16

Primera línea del párrafo narrativo.
Segunda línea de epicrisis previa.
"""
    spans = build_spans_from_text(text, doc="epicrisis", session_id="case2")
    kinds = {span.kind for span in spans}
    assert SpanKind.HEADING in kinds
    assert SpanKind.RESULT_LINE in kinds
    assert SpanKind.PARAGRAPH in kinds


def test_build_spans_from_text_labs_pdf_like_without_pipes() -> None:
    text = """Hemoglobina 9.8 g/dL
Hematocrito 30.1 %
Fecha de toma: 2025-11-12"""
    spans = build_spans_from_text(text, doc="labs", session_id="case1")
    result_lines = [span for span in spans if span.kind == SpanKind.RESULT_LINE]
    assert len(result_lines) >= 2
    assert all(span.kind != SpanKind.PARAGRAPH for span in result_lines)
    texts = {span.text for span in result_lines}
    assert "Hemoglobina 9.8 g/dL" in texts
    assert "Hematocrito 30.1 %" in texts


def test_build_spans_from_text_detects_result_with_out_of_range_marker() -> None:
    text = "Glucosa en ayunas 112 ALTO mg/dL 70 - 99"
    spans = build_spans_from_text(text, doc="labs", session_id="case1")
    assert len(spans) == 1
    assert spans[0].kind == SpanKind.RESULT_LINE
    assert spans[0].text == text


def test_build_spans_from_text_wrapped_prose_stays_single_paragraph() -> None:
    text = """Primera línea del párrafo narrativo clínico.
Segunda línea que continúa la misma idea sin estructura.
Tercera línea cerrando el párrafo envuelto."""
    spans = build_spans_from_text(text, doc="epicrisis", session_id="case2")
    paragraphs = [span for span in spans if span.kind == SpanKind.PARAGRAPH]
    assert len(paragraphs) == 1
    assert "Primera línea" in paragraphs[0].text
    assert "Tercera línea" in paragraphs[0].text


@pytest.mark.skipif(not CASE1_LAB_PDF.is_file(), reason="case1 lab PDF fixture missing")
def test_build_spans_from_pdf_case1_lab_anemia() -> None:
    spans = build_spans_from_pdf(
        CASE1_LAB_PDF,
        doc="case1_lab_results",
        session_id="case1",
    )
    result_lines = [span for span in spans if span.kind == SpanKind.RESULT_LINE]
    assert len(result_lines) >= 2


def test_build_spans_from_text_assigns_numeric_ids() -> None:
    text = """# Laboratorio

HEMOGLOBINA | 9.2 g/dL | VR 12-16
"""
    spans = build_spans_from_text(text, doc="epicrisis", session_id="case2")
    assert spans
    assert spans[0].id == "1"
    assert all(span.id.isdigit() for span in spans)
    assert len({span.id for span in spans}) == len(spans)


def test_merge_spans_renumbers_to_global_numeric_ids() -> None:
    left = [Span(id="local_a", doc="doc", kind=SpanKind.LINE, text="a")]
    right = [Span(id="local_b", doc="doc", kind=SpanKind.LINE, text="b")]
    merged = merge_spans(left, right)
    assert [span.id for span in merged] == ["1", "2"]


def test_build_adapter_jobs_inverts_cluster_assignments() -> None:
    template = load_template("minimal_outpatient_v001")
    classify_result = ClassifyClustersResult(
        assignments=[
            {"cluster_id": "c1", "section_ids": ["antecedentes", "revision_sistemas"]},
            {"cluster_id": "c2", "section_ids": ["examen_fisico"]},
        ]
    )
    jobs = build_adapter_jobs(classify_result, template.section_id_set())
    assert jobs["antecedentes"] == ["c1"]
    assert jobs["revision_sistemas"] == ["c1"]
    assert jobs["examen_fisico"] == ["c2"]
    assert "motivo_consulta" not in jobs


def test_build_adapter_jobs_skips_dropped_clusters_with_empty_section_ids() -> None:
    template = load_template("minimal_outpatient_v001")
    classify_result = ClassifyClustersResult(
        assignments=[
            {"cluster_id": "c1", "section_ids": ["antecedentes"]},
            {"cluster_id": "c2", "section_ids": []},
        ]
    )
    jobs = build_adapter_jobs(classify_result, template.section_id_set())
    assert jobs == {"antecedentes": ["c1"]}
    assert classify_result.dropped_cluster_ids() == ["c2"]


def test_audit_triage_result_rejects_unknown_id() -> None:
    items = [DoctorItem(id="1", text="contenido")]
    result = TriageResult(content_ids=["9"], drop_ids=[])
    with pytest.raises(ValueError, match="unknown_item_id"):
        audit_triage_result(items, result)


def test_audit_filter_spans_result_rejects_unknown_span_id() -> None:
    spans = [Span(id="s1", doc="doc", kind=SpanKind.LINE, text="x")]
    result = FilterSpansResult(drop_ids=["missing"])
    with pytest.raises(ValueError, match="unknown_span_id"):
        audit_filter_spans_result(spans, result)


def test_audit_span_clusters_rejects_unknown_span_in_cluster() -> None:
    spans = [Span(id="s1", doc="doc", kind=SpanKind.LINE, text="x")]
    clusters = [SpanCluster(id="c1", span_ids=["s1", "s2"])]
    with pytest.raises(ValueError, match="unknown_span_id"):
        audit_span_clusters(spans, clusters)


def test_audit_span_clusters_requires_complete_coverage_when_enabled() -> None:
    spans = [
        Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a"),
        Span(id="s2", doc="doc", kind=SpanKind.LINE, text="b"),
    ]
    clusters = [SpanCluster(id="c1", span_ids=["s1"], title="tema_a")]
    with pytest.raises(ValueError, match="missing_span_ids"):
        audit_span_clusters(
            spans,
            clusters,
            require_complete_span_coverage=True,
            require_titles=True,
        )


def test_audit_span_clusters_requires_title_when_enabled() -> None:
    spans = [Span(id="s1", doc="doc", kind=SpanKind.LINE, text="a")]
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    with pytest.raises(ValueError, match="missing_title"):
        audit_span_clusters(
            spans,
            clusters,
            require_complete_span_coverage=True,
            require_titles=True,
        )


def test_audit_classify_clusters_rejects_unknown_section() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    result = ClassifyClustersResult(
        assignments=[{"cluster_id": "c1", "section_ids": ["not_a_section"]}]
    )
    with pytest.raises(ValueError, match="unknown_section_id"):
        audit_classify_clusters(clusters, template, result)


def test_audit_section_adapter_result_rejects_mismatch() -> None:
    result = SectionAdapterResult(section_id="otra", brief="texto")
    with pytest.raises(ValueError, match="section_id_mismatch"):
        audit_section_adapter_result("antecedentes", result)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fecha de toma: 2025-11-12", "2025-11-12"),
        ("Epicrisis del 15/03/2024", "2024-03-15"),
        ("Ingreso 12-08-2019", "2019-08-12"),
        ("marzo de 2024", "marzo de 2024"),
        ("hace 3 meses", "hace 3 meses"),
        ("desde hace 2 semanas", "desde hace 2 semanas"),
        ("diagnosticado en 2018", "en 2018"),
    ],
)
def test_detect_date_hint_matches_explicit_dates(text: str, expected: str) -> None:
    assert detect_date_hint(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "TA 120/80",
        "Hemoglobina 9.8 g/dL",
        "rango 10-20",
        "sin fecha relevante",
    ],
)
def test_detect_date_hint_avoids_clinical_false_positives(text: str) -> None:
    assert detect_date_hint(text) is None


def test_build_spans_from_text_sets_date_hint_on_spans() -> None:
    spans = build_spans_from_text(
        "Epicrisis de marzo de 2024.\n\nHemoglobina 9.8 g/dL",
        doc="epicrisis",
        session_id="case2",
    )
    dated = [span for span in spans if span.date_hint is not None]
    assert any(span.date_hint == "marzo de 2024" for span in dated)


def test_propagate_cluster_date_hints_collects_in_span_order_deduped() -> None:
    spans = [
        Span(id="s1", doc="d", kind=SpanKind.LINE, text="a", date_hint="2024-03-15"),
        Span(id="s2", doc="d", kind=SpanKind.LINE, text="b", date_hint="marzo de 2024"),
        Span(id="s3", doc="d", kind=SpanKind.LINE, text="c", date_hint="2024-03-15"),
    ]
    clusters = [SpanCluster(id="c1", span_ids=["s1", "s2", "s3"])]
    enriched = propagate_cluster_date_hints(clusters, spans)
    assert enriched[0].date_hints == ["2024-03-15", "marzo de 2024"]


def test_cluster_to_payload_item_omits_empty_date_hints() -> None:
    cluster = SpanCluster(id="c1", span_ids=["s1"])
    payload = cluster_to_payload_item(cluster)
    assert "date_hints" not in payload


def test_cluster_to_payload_item_includes_date_hints_when_present() -> None:
    cluster = SpanCluster(id="c1", span_ids=["s1"], date_hints=["marzo de 2024"])
    payload = cluster_to_payload_item(cluster)
    assert payload["date_hints"] == ["marzo de 2024"]
