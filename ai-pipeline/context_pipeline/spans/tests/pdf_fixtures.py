from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def write_text_pdf(path: Path, *, lines: list[str]) -> None:
    """Test helper: build a readable PDF with embedded text lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter)
    y_position = 750.0
    for line in lines:
        pdf.drawString(50, y_position, line)
        y_position -= 16
    pdf.save()


def write_columnar_pdf(path: Path, *, rows: list[list[tuple[float, str]]]) -> None:
    """Test helper: build a PDF placing text at explicit x positions per row.

    Each row is a list of ``(x, text)`` cells drawn on the same baseline, so the
    output reproduces the multi-column lab layouts that pdfplumber glues into a
    single text line (label / value / reference-range columns).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter)
    y_position = 750.0
    for row in rows:
        for x, text in row:
            pdf.drawString(x, y_position, text)
        y_position -= 18
    pdf.save()
