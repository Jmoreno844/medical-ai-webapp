from app.domains.documents.content import (
    build_synced_document_content,
    get_empty_tiptap_doc,
    markdown_to_tiptap_json,
    tiptap_json_to_markdown,
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


def test_markdown_source_parses_formatting_for_tiptap() -> None:
    content_json = markdown_to_tiptap_json(
        "# Plan\n\nPaciente con **dolor** leve.\n\n- Control\n- Reposo"
    )

    assert content_json["content"][0] == {
        "type": "heading",
        "attrs": {"level": 1},
        "content": [{"type": "text", "text": "Plan"}],
    }
    paragraph = content_json["content"][1]
    assert paragraph["type"] == "paragraph"
    assert paragraph["content"][1] == {
        "type": "text",
        "text": "dolor",
        "marks": [{"type": "bold"}],
    }
    assert content_json["content"][2]["type"] == "bulletList"


def test_tiptap_json_round_trips_basic_markdown_marks() -> None:
    content_json = markdown_to_tiptap_json("## Nota\n\nPaciente con **dolor**.")

    assert tiptap_json_to_markdown(content_json) == "## Nota\n\nPaciente con **dolor**."

