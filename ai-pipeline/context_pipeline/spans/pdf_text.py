from __future__ import annotations

from pathlib import Path

# Tolerancia (px) para asignar palabras a un renglón por su coordenada vertical (top).
PDF_LINE_TOP_TOL = 3.0


def pdf_to_text(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"extract_pdf_not_found: {path}")

    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
    return "\n\n".join(pages)


def _lines_from_words(words: list[dict]) -> list[dict]:
    """Fallback: synthesize visual lines by grouping words with the same top."""
    buckets: dict[int, list[dict]] = {}
    for word in words:
        buckets.setdefault(round(float(word["top"])), []).append(word)
    lines: list[dict] = []
    for top in sorted(buckets):
        row = sorted(buckets[top], key=lambda w: float(w["x0"]))
        lines.append(
            {
                "text": " ".join(str(w["text"]) for w in row),
                "top": float(top),
                "x0": float(row[0]["x0"]),
                "x1": float(row[-1]["x1"]),
            }
        )
    return lines


def pdf_to_lines(path: Path) -> list[dict]:
    """Extract visual lines with geometry plus their words.

    Returns one dict per visual line: ``{text, top, x0, x1, words}`` where
    ``words`` is ``[{text, x0, x1}, ...]`` sorted left-to-right. Callers use the
    word x-coordinates to detect and split multi-column rows that pdfplumber's
    flattened ``extract_text`` would otherwise glue into a single line.
    """
    if not path.is_file():
        raise ValueError(f"extract_pdf_not_found: {path}")

    import pdfplumber

    lines: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            try:
                text_lines = page.extract_text_lines()
            except (AttributeError, NotImplementedError):
                text_lines = _lines_from_words(words)
            for text_line in text_lines:
                top = float(text_line["top"])
                line_words = sorted(
                    (
                        w
                        for w in words
                        if abs(float(w["top"]) - top) <= PDF_LINE_TOP_TOL
                    ),
                    key=lambda w: float(w["x0"]),
                )
                lines.append(
                    {
                        "text": str(text_line.get("text", "")).strip(),
                        "top": top,
                        "x0": float(text_line.get("x0", 0.0)),
                        "x1": float(text_line.get("x1", 0.0)),
                        "words": [
                            {
                                "text": str(w["text"]),
                                "x0": float(w["x0"]),
                                "x1": float(w["x1"]),
                            }
                            for w in line_words
                        ],
                    }
                )
    return lines


def chunk_text_by_tokens(
    text: str,
    *,
    max_tokens: int,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    import tiktoken

    if max_tokens <= 0:
        raise ValueError("extract_chunk_max_tokens_must_be_positive")
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_text = encoding.decode(tokens[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text.strip())
        start = end
    return chunks


__all__ = ["chunk_text_by_tokens", "pdf_to_lines", "pdf_to_text"]
