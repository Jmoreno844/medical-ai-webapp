from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("encounters", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CopilotRun",
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
                ("run_id", models.CharField(max_length=64, unique=True)),
                ("thread_id", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="created",
                        max_length=32,
                    ),
                ),
                ("intent", models.CharField(blank=True, max_length=64, null=True)),
                ("requires_human_review", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "encounter",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="copilot_runs",
                        to="encounters.encounter",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="copilotrun",
            index=models.Index(fields=["doctor", "encounter"], name="copilot_run_doctor__3ca49a_idx"),
        ),
        migrations.AddIndex(
            model_name="copilotrun",
            index=models.Index(fields=["thread_id"], name="copilot_run_thread__6fa655_idx"),
        ),
    ]

