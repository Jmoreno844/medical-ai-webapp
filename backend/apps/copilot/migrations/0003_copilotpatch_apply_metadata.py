from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("copilot", "0002_copilotpatch_waiting_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="copilotpatch",
            name="source_context_document_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="target_selection_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="copilotpatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("applied", "Applied"),
                    ("stale", "Stale"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
    ]
