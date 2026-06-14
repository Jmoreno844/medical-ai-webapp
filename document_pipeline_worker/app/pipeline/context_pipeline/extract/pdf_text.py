from __future__ import annotations

from pathlib import Path


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


def chunk_text_by_tokens(
    text: str,
    *,
    max_tokens: int,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """Split extracted PDF text so each chunk fits the extract LLM token budget."""
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
