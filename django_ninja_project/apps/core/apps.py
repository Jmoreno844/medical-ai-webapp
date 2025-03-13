from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"  # This must match exactly the actual Python path to the app
    verbose_name = "Core"
