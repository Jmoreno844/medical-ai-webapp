from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0002_initial"),
        ("encounters", "0002_initial"),
        ("copilot", "0005_rename_copilot_pat_run_id_7b4750_idx_copilot_cop_run_id_468f25_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CopilotPatchSet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("patch_set_id", models.CharField(max_length=64, unique=True)),
                ("base_version", models.IntegerField(default=1)),
                ("base_hash", models.CharField(max_length=128)),
                ("rationale", models.TextField(blank=True, null=True)),
                ("source_context_document_ids", models.JSONField(blank=True, default=list)),
                ("target_document_title", models.CharField(blank=True, max_length=255, null=True)),
                ("target_selection_reason", models.TextField(blank=True, null=True)),
                ("document_preview_after", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("partially_accepted", "Partially Accepted"),
                            ("accepted", "Accepted"),
                            ("rejected", "Rejected"),
                            ("stale", "Stale"),
                            ("applied", "Applied"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("review_comment", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_patch_sets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "encounter",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_patch_sets",
                        to="encounters.encounter",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="patch_sets",
                        to="copilot.copilotrun",
                    ),
                ),
                (
                    "target_document",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_patch_sets",
                        to="documents.document",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="conflict_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="new_text",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="old_text",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="order_index",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="patch_set",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="patches",
                to="copilot.copilotpatchset",
            ),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="patch_type",
            field=models.CharField(default="rewrite_document", max_length=64),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="resolved_end",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="copilotpatch",
            name="resolved_start",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="copilotpatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("rejected", "Rejected"),
                    ("conflicted", "Conflicted"),
                    ("applied", "Applied"),
                    ("stale", "Stale"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatchset",
            index=models.Index(
                fields=["run", "status"],
                name="copilot_pset_run_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatchset",
            index=models.Index(
                fields=["doctor", "encounter"],
                name="copilot_pset_doctor_enc_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatchset",
            index=models.Index(
                fields=["target_document"],
                name="copilot_pset_target_doc_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatch",
            index=models.Index(
                fields=["patch_set", "status"],
                name="copilot_patch_pset_status_idx",
            ),
        ),
    ]
