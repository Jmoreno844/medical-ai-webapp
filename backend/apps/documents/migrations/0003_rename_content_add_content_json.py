from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="document",
            old_name="content",
            new_name="content_markdown",
        ),
        migrations.AlterField(
            model_name="document",
            name="content_markdown",
            field=models.TextField(default=""),
        ),
        migrations.AddField(
            model_name="document",
            name="content_json",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
