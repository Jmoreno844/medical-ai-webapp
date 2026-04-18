from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.copilot.api import _serialize_patch
from apps.copilot.services.patch_sets import (
    apply_accepted_patch_set,
    content_hash,
)
from apps.documents.services.rich_document_content import (
    markdown_to_tiptap_json,
    tiptap_json_to_markdown,
)


class CopilotPatchApplySyncTests(SimpleTestCase):
    def test_serialize_patch_exposes_typed_anchor_and_normalized_operation(self):
        patch = SimpleNamespace(
            patch_id="patch-1",
            patch_set_id=10,
            patch_set=SimpleNamespace(patch_set_id="pset-1"),
            run=SimpleNamespace(run_id="run-1"),
            target_document_id=42,
            base_version=3,
            order_index=0,
            patch_type="insert_after",
            operation_type="insert_after_span",
            anchor={
                "exactText": "Plan de manejo",
                "prefixText": "Analisis clinico",
                "suffixText": "Control",
                "startOffset": 10,
                "endOffset": 24,
            },
            expected_hash=None,
            old_text="Plan de manejo",
            new_text="\nControl en 2 semanas",
            resolved_start=10,
            resolved_end=24,
            confidence=None,
            conflict_reason=None,
            replacement_text=None,
            inserted_text="\nControl en 2 semanas",
            document_preview_after=None,
            content_preview="\nControl en 2 semanas",
            rationale="Agrega seguimiento",
            source_context_document_ids=[],
            target_document_title="Nota",
            target_selection_reason=None,
            status="pending",
            review_comment=None,
            section="plan_manejo",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

        serialized = _serialize_patch(patch)

        self.assertEqual(serialized["operation_type"], "insert_after_span")
        self.assertEqual(serialized["normalized_operation_type"], "insert_after")
        self.assertEqual(serialized["anchor"]["exactText"], "Plan de manejo")
        self.assertEqual(serialized["section"], "plan_manejo")
        self.assertEqual(serialized["inserted_text"], "\nControl en 2 semanas")

    def test_apply_accepted_patch_set_keeps_markdown_and_json_aligned(self):
        doctor = SimpleNamespace(id=4)
        document = SimpleNamespace(
            id=31,
            content_markdown="## Analisis clinico\n\nPaciente estable.",
            content_json=markdown_to_tiptap_json(
                "## Analisis clinico\n\nPaciente estable."
            ),
            save=Mock(),
        )
        document.content = document.content_markdown
        accepted_patch = SimpleNamespace(
            pk=101,
            patch_id="patch-sync-1",
            patch_type="replace_span",
            resolved_start=document.content_markdown.index("estable"),
            resolved_end=document.content_markdown.index("estable")
            + len("estable"),
            new_text="estable, sin signos de alarma",
            order_index=0,
        )
        pending_filter = Mock()
        pending_filter.exists.return_value = False
        accepted_filter = Mock()
        accepted_filter.order_by.return_value = [accepted_patch]
        accepted_update_filter = Mock()
        accepted_update_filter.update.return_value = 1
        patches_manager = Mock()

        def filter_patches(*args, **kwargs):
            if kwargs == {"status": "pending"}:
                return pending_filter
            if kwargs == {"status": "accepted"}:
                return accepted_filter
            if kwargs == {"pk__in": [accepted_patch.pk]}:
                return accepted_update_filter
            raise AssertionError(f"Unexpected patch filter kwargs: {kwargs}")

        patches_manager.filter.side_effect = filter_patches
        patch_set = SimpleNamespace(
            pk=55,
            patch_set_id="pset-sync-1",
            doctor=doctor,
            target_document=document,
            base_version=1,
            base_hash=content_hash(document.content_markdown),
            status="accepted",
            patches=patches_manager,
            review_comment=None,
            document_preview_after=None,
            save=Mock(),
        )

        stale_patch_sets = Mock()
        stale_patch_sets.exclude.return_value = stale_patch_sets
        stale_patch_sets.values_list.return_value = []
        stale_patch_sets.update.return_value = 0

        stale_patch_records = Mock()
        stale_patch_records.exclude.return_value = stale_patch_records
        stale_patch_records.values_list.return_value = []
        stale_patch_records.update.return_value = 0

        with (
            patch(
                "apps.copilot.services.patch_sets.CopilotPatchSet.objects.filter",
                return_value=stale_patch_sets,
            ),
            patch(
                "apps.copilot.services.patch_sets.CopilotPatch.objects.filter",
                return_value=stale_patch_records,
            ),
            patch(
                "apps.copilot.services.patch_sets._update_patch_set_status_from_children",
                return_value="applied",
            ),
        ):
            result = apply_accepted_patch_set.__wrapped__(patch_set=patch_set)

        self.assertEqual(
            document.content_markdown,
            "## Analisis clinico\n\nPaciente estable, sin signos de alarma.",
        )
        self.assertEqual(result.content, document.content_markdown)
        self.assertIsNotNone(document.content_json)
        self.assertEqual(
            tiptap_json_to_markdown(document.content_json),
            document.content_markdown,
        )
        document.save.assert_called_once_with(
            update_fields=["content_markdown", "content_json"]
        )
        accepted_update_filter.update.assert_called_once_with(
            status="applied",
            review_comment=None,
        )
        self.assertEqual(patch_set.status, "applied")
