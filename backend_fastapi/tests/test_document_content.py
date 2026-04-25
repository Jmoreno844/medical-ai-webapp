from app.domains.documents.content import (
    build_synced_document_content,
    get_empty_tiptap_doc,
)


def test_empty_document_content_uses_tiptap_doc_shape() -> None:
    synced = build_synced_document_content()

    assert synced.content_markdown == ""
    assert synced.content_json == get_empty_tiptap_doc()


def test_json_source_normalizes_and_renders_text() -> None:
    synced = build_synced_document_content(
        content_json={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hola"}],
                }
            ],
        },
        preferred_source="json",
    )

    assert synced.content_markdown == "Hola"
    assert synced.content_json["type"] == "doc"

