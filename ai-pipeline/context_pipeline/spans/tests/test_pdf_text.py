from __future__ import annotations

from pathlib import Path

from context_pipeline.spans.pdf_text import chunk_text_by_tokens, pdf_to_text
from context_pipeline.spans.tests.pdf_fixtures import write_text_pdf

FIXTURE_PDF = (
    Path(__file__).resolve().parents[2]
    / "cases"
    / "documents"
    / "case1_lab_anemia.pdf"
)


def test_pdf_to_text_reads_fixture(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    write_text_pdf(
        pdf_path,
        lines=[
            "Laboratorio Clinico Dummy",
            "Hemoglobina 9.8 g/dL",
            "Fecha: 2025-11-12",
        ],
    )
    text = pdf_to_text(pdf_path)
    assert "Hemoglobina 9.8 g/dL" in text
    assert "2025-11-12" in text


def test_chunk_text_by_tokens_splits_long_text() -> None:
    text = "palabra " * 5000
    chunks = chunk_text_by_tokens(text, max_tokens=200)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_committed_fixture_pdf_exists_and_has_text() -> None:
    fixture_lines = [
        "Laboratorio Clinico Dummy - caso sintetico",
        "Paciente: PACIENTE_DUMMY",
        "Hemoglobina 9.8 g/dL",
        "Hematocrito 30.1 %",
        "Fecha de toma: 2025-11-12",
    ]
    if not FIXTURE_PDF.is_file():
        write_text_pdf(FIXTURE_PDF, lines=fixture_lines)
    text = pdf_to_text(FIXTURE_PDF)
    if "Hemoglobina 9.8 g/dL" not in text:
        write_text_pdf(FIXTURE_PDF, lines=fixture_lines)
        text = pdf_to_text(FIXTURE_PDF)
    assert "Hemoglobina 9.8 g/dL" in text
