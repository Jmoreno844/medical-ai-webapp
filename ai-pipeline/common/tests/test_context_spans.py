from __future__ import annotations

from pathlib import Path

import pytest

from common.context_spans import (
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
    doctor_items_to_spans,
    merge_spans,
    split_doctor_items,
)
from common.templates import load_template

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
    assert [item.id for item in items] == ["m1", "m2"]
    assert items[0].text == "TA 138/88."
    assert items[1].text == "Paciente pálido."


def test_split_doctor_items_detects_pasted_by_tokens() -> None:
    long_note = " ".join(["línea clínica repetida"] * 80)
    _, is_pasted = split_doctor_items(long_note, session_id="case3")
    assert is_pasted is True


def test_doctor_items_to_spans_filters_content_ids() -> None:
    items = [
        DoctorItem(id="m1", text="Alergia a penicilina."),
        DoctorItem(id="m2", text="Directiva ignorar epicrisis."),
    ]
    spans = doctor_items_to_spans(items, ["m1"])
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


def test_merge_spans_rejects_duplicate_ids() -> None:
    span = Span(id="doc_s0001", doc="doc", kind=SpanKind.LINE, text="a")
    with pytest.raises(ValueError, match="duplicate_span_id"):
        merge_spans([span], [span])


def test_build_adapter_jobs_inverts_cluster_assignments() -> None:
    template = load_template("minimal_outpatient_v001")
    classify_result = ClassifyClustersResult(
        assignments={
            "c1": ["antecedentes", "revision_sistemas"],
            "c2": ["examen_fisico"],
        }
    )
    jobs = build_adapter_jobs(classify_result, template.section_id_set())
    assert jobs["antecedentes"] == ["c1"]
    assert jobs["revision_sistemas"] == ["c1"]
    assert jobs["examen_fisico"] == ["c2"]
    assert "motivo_consulta" not in jobs


def test_audit_triage_result_rejects_unknown_id() -> None:
    items = [DoctorItem(id="m1", text="contenido")]
    result = TriageResult(content_ids=["m9"], drop_ids=[])
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


def test_audit_classify_clusters_rejects_unknown_section() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [SpanCluster(id="c1", span_ids=["s1"])]
    result = ClassifyClustersResult(assignments={"c1": ["not_a_section"]})
    with pytest.raises(ValueError, match="unknown_section_id"):
        audit_classify_clusters(clusters, template, result)


def test_audit_section_adapter_result_rejects_mismatch() -> None:
    result = SectionAdapterResult(section_id="otra", content="texto")
    with pytest.raises(ValueError, match="section_id_mismatch"):
        audit_section_adapter_result("antecedentes", result)
