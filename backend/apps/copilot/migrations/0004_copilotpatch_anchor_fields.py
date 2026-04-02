from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("copilot", "0003_copilotpatch_apply_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="copilotpatch",
            name="after_preview",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="anchor",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="before_preview",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="document_preview_after",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="expected_hash",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="target_document_title",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
