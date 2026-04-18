from django.db import migrations, models


def backfill_applicable_text(apps, _schema_editor):
    CopilotPatch = apps.get_model("copilot", "CopilotPatch")
    insert_types = {"insert_before", "insert_after", "insert_after_span"}
    rewrite_types = {"rewrite_document"}
    for patch in CopilotPatch.objects.all().iterator():
        patch_type = (patch.patch_type or patch.operation_type or "").strip().lower()
        operation_type = (patch.operation_type or patch_type).strip().lower()
        text_source = patch.new_text or patch.content_preview or patch.after_preview
        update_fields = []
        if operation_type in rewrite_types or patch_type in rewrite_types:
            patch.replacement_text = (
                patch.document_preview_after or text_source or patch.content_preview or ""
            )
            update_fields.append("replacement_text")
        elif operation_type in insert_types or patch_type in insert_types:
            patch.inserted_text = patch.content_preview or text_source or ""
            update_fields.append("inserted_text")
        elif operation_type == "replace_span" or patch_type == "replace_span":
            patch.replacement_text = text_source or ""
            update_fields.append("replacement_text")

        if update_fields:
            patch.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("copilot", "0007_add_clinical_plan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="copilotpatch",
            name="replacement_text",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="inserted_text",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_applicable_text, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="copilotpatch",
            name="before_preview",
        ),
        migrations.RemoveField(
            model_name="copilotpatch",
            name="after_preview",
        ),
    ]
