from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.documents.api.base import update_document_by_editor
from apps.documents.api.callbacks import update_document_by_function
from apps.documents.schemas import DocumentContentUpdateIn
from apps.documents.services.rich_document_content import (
    markdown_to_tiptap_json,
    set_document_content_fields,
    tiptap_json_to_markdown,
)
from apps.documents.services.document_sections import extract_document_sections


class RichDocumentContentServiceTests(SimpleTestCase):
    def test_markdown_round_trip_supports_editor_subset(self):
        markdown = (
            "# Nota clinica\n\n"
            "Paciente con **dolor** y *fatiga*.\n\n"
            "- presente\n"
            "- ausente\n\n"
            "> observacion clinica\n\n"
            "```sql\nSELECT 1;\n```\n\n"
            "| Columna | Valor |\n"
            "| --- | --- |\n"
            "| Enlace | [sitio](https://example.com) |"
        )

        content_json = markdown_to_tiptap_json(markdown)
        rendered = tiptap_json_to_markdown(content_json)

        self.assertEqual(content_json["type"], "doc")
        self.assertIn("content", content_json)
        self.assertIn("# Nota clinica", rendered)
        self.assertIn("**dolor**", rendered)
        self.assertIn("*fatiga*", rendered)
        self.assertIn("- presente", rendered)
        self.assertIn("> observacion clinica", rendered)
        self.assertIn("```sql", rendered)
        self.assertIn("| Columna | Valor |", rendered)
        self.assertIn("[sitio](https://example.com)", rendered)

    def test_legacy_markdown_setter_keeps_json_in_sync(self):
        document = SimpleNamespace(content_markdown="", content_json=None)

        set_document_content_fields(
            document,
            content_markdown="## Analisis clinico\n\nPaciente estable.",
            preferred_source="markdown",
        )

        self.assertEqual(
            document.content_markdown,
            "## Analisis clinico\n\nPaciente estable.",
        )
        self.assertIsInstance(document.content_json, dict)
        self.assertEqual(document.content_json["type"], "doc")

    def test_extract_document_sections_detects_literal_headings(self):
        sections_payload = extract_document_sections(
            content_markdown=(
                "## Enfermedad actual\n\n"
                "Paciente con dolor abdominal.\n\n"
                "## Conducta\n\n"
                "Analgesia y control.\n"
            ),
        )

        self.assertEqual(sections_payload["structure_mode"], "structured")
        self.assertEqual(
            [section["section_id"] for section in sections_payload["sections"]],
            ["enfermedad_actual", "conducta"],
        )
        self.assertEqual(
            sections_payload["sections"][1]["resolution_source"],
            "literal_heading",
        )

    def test_extract_document_sections_falls_back_to_derived_heading_ids(self):
        sections_payload = extract_document_sections(
            content_markdown=(
                "## Valoracion integral\n\n"
                "Paciente estable.\n\n"
                "## Recomendaciones de alta\n\n"
                "Control ambulatorio.\n"
            ),
        )

        self.assertEqual(sections_payload["structure_mode"], "structured")
        self.assertEqual(
            [section["section_id"] for section in sections_payload["sections"]],
            ["valoracion_integral", "recomendaciones_de_alta"],
        )
        self.assertEqual(
            sections_payload["sections"][0]["resolution_source"],
            "literal_heading",
        )


class DocumentDualContentApiTests(SimpleTestCase):
    def test_editor_write_path_prefers_json_and_regenerates_markdown(self):
        doctor = SimpleNamespace(id=7)
        document = SimpleNamespace(
            id=31,
            doctor=doctor,
            content_markdown="Texto inicial",
            content_json=markdown_to_tiptap_json("Texto inicial"),
            save=Mock(),
        )
        payload = DocumentContentUpdateIn(
            content="IGNORAR",
            content_markdown="IGNORAR",
            content_json={
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 2},
                        "content": [{"type": "text", "text": "Analisis clinico"}],
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Texto desde json"}],
                    },
                ],
            },
        )

        with patch("apps.documents.api.base.get_object_or_404", return_value=document):
            response = update_document_by_editor(
                SimpleNamespace(user=doctor),
                document.id,
                payload,
            )

        self.assertTrue(response["success"])
        self.assertEqual(document.content_markdown, "## Analisis clinico\n\nTexto desde json")
        self.assertEqual(document.content_json["type"], "doc")
        document.save.assert_called_once_with(
            update_fields=["content_markdown", "content_json"]
        )

    def test_function_write_path_prefers_markdown_and_regenerates_json(self):
        doctor = SimpleNamespace(id=9)
        document = SimpleNamespace(
            id=42,
            doctor=doctor,
            content_markdown="Texto inicial",
            content_json=markdown_to_tiptap_json("Texto inicial"),
            save=Mock(),
        )
        payload = DocumentContentUpdateIn(
            content_markdown="## Plan\n\n- analgesia\n- control",
            content_json={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "JSON que no debe ganar"}],
                    }
                ],
            },
        )

        with patch(
            "apps.documents.api.callbacks.get_object_or_404",
            return_value=document,
        ):
            response = update_document_by_function(
                request=None,
                document_id=document.id,
                payload=payload,
                auth={"document_id": document.id, "user_id": doctor.id},
            )

        self.assertTrue(response["success"])
        self.assertEqual(document.content_markdown, "## Plan\n\n- analgesia\n- control")
        self.assertEqual(
            tiptap_json_to_markdown(document.content_json),
            document.content_markdown,
        )
        document.save.assert_called_once_with(
            update_fields=["content_markdown", "content_json"]
        )
