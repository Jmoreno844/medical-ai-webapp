from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)


def pdf_to_text(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"extract_pdf_not_found: {path}")
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
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


def write_text_pdf(path: Path, *, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content_lines = ["BT", "/F1 12 Tf", "50 750 Td"]
    for index, line in enumerate(lines):
        escaped = (
            line.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        if index > 0:
            content_lines.append("0 -16 Td")
        content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(content_lines).encode("latin-1"))

    page = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Page"),
            NameObject("/Parent"): None,
            NameObject("/MediaBox"): [
                NumberObject(0),
                NumberObject(0),
                NumberObject(612),
                NumberObject(792),
            ],
            NameObject("/Contents"): stream,
            NameObject("/Resources"): DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {
                            NameObject("/F1"): DictionaryObject(
                                {
                                    NameObject("/Type"): NameObject("/Font"),
                                    NameObject("/Subtype"): NameObject("/Type1"),
                                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                                }
                            )
                        }
                    )
                }
            ),
        }
    )

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.pages[0][NameObject("/Contents")] = stream
    writer.pages[0][NameObject("/Resources")] = page["/Resources"]
    with path.open("wb") as handle:
        writer.write(handle)
