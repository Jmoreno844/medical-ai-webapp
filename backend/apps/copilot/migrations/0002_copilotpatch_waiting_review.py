from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0002_initial"),
        ("encounters", "0002_initial"),
        ("copilot", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="copilotrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("created", "Created"),
                    ("running", "Running"),
                    ("waiting_review", "Waiting Review"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="created",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="CopilotPatch",
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
                ("patch_id", models.CharField(max_length=64, unique=True)),
                ("base_version", models.IntegerField(default=1)),
                ("operation_type", models.CharField(max_length=64)),
                ("content_preview", models.TextField()),
                ("rationale", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("stale", "Stale"),
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
                        related_name="copilot_patches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "encounter",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_patches",
                        to="encounters.encounter",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="patches",
                        to="copilot.copilotrun",
                    ),
                ),
                (
                    "target_document",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_patches",
                        to="documents.document",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="copilotpatch",
            index=models.Index(
                fields=["run", "status"],
                name="copilot_pat_run_id_7b4750_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatch",
            index=models.Index(
                fields=["doctor", "encounter"],
                name="copilot_pat_doctor__7d2b7d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="copilotpatch",
            index=models.Index(
                fields=["target_document"],
                name="copilot_pat_target__95b0e8_idx",
            ),
        ),
    ]
