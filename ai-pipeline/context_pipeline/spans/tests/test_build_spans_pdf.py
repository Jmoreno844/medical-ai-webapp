from __future__ import annotations

from pathlib import Path

from common.context_spans import SpanKind, build_spans_from_pdf, span_to_payload_item
from context_pipeline.spans.tests.pdf_fixtures import write_columnar_pdf


def test_build_spans_from_pdf_splits_merged_columns(tmp_path: Path) -> None:
    pdf_path = tmp_path / "hgc.pdf"
    write_columnar_pdf(
        pdf_path,
        rows=[
            [(50, "HORMONAS")],
            [
                (50, "Resultado"),
                (200, "16.735 mUI/ml"),
                (450, "No embarazadas: ND - 5,3 mUI/ml"),
            ],
            [(50, "Hemoglobina 9.8 g/dL")],
        ],
    )

    spans = build_spans_from_pdf(pdf_path, doc="hgc", session_id="case")
    texts = [span.text for span in spans]

    # La fila multicolumna se separó: el resultado quedó aparte de la referencia.
    assert any("16.735 mUI/ml" in t and "No embarazadas" not in t for t in texts)
    assert any("No embarazadas" in t for t in texts)

    # Los spans de esa fila quedan marcados como fusión de columnas.
    merged = [span for span in spans if "merged_columns" in span.flags]
    assert merged
    # El flag viaja al payload que ve filter_spans.
    assert "flags" in span_to_payload_item(merged[0])

    # Una línea de una sola columna no se marca y se clasifica como result_line.
    hemo = [span for span in spans if "Hemoglobina" in span.text]
    assert hemo
    assert hemo[0].kind == SpanKind.RESULT_LINE
    assert not hemo[0].flags


def test_build_spans_from_pdf_keeps_single_column_lines(tmp_path: Path) -> None:
    pdf_path = tmp_path / "simple.pdf"
    write_columnar_pdf(
        pdf_path,
        rows=[
            [(50, "Hemoglobina 9.8 g/dL")],
            [(50, "Hematocrito 30.1 %")],
        ],
    )

    spans = build_spans_from_pdf(pdf_path, doc="lab", session_id="case")

    # Cada analito es un span result_line separado, sin flags de fusión.
    result_lines = [s for s in spans if s.kind == SpanKind.RESULT_LINE]
    assert len(result_lines) == 2
    assert all(not s.flags for s in spans)


def test_build_spans_from_pdf_recombines_lab_label_value_and_range_columns(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "cmp.pdf"
    write_columnar_pdf(
        pdf_path,
        rows=[
            [(50, "Potasio"), (220, "4.3 mmol/L"), (380, "3.5 - 5.1")],
            [(50, "ALT (TGP)"), (220, "31 U/L"), (380, "7 - 56")],
        ],
    )

    spans = build_spans_from_pdf(pdf_path, doc="cmp", session_id="case")

    assert len(spans) == 2
    assert spans[0].text == "Potasio 4.3 mmol/L 3.5 - 5.1"
    assert spans[1].text == "ALT (TGP) 31 U/L 7 - 56"
    assert all(span.kind == SpanKind.RESULT_LINE for span in spans)
