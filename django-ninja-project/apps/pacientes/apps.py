from django.apps import AppConfig


class PacientesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pacientes"
    verbose_name = "Pacientes"

    def ready(self):
        try:
            import apps.pacientes.signals  # noqa F401
        except ImportError:
            pass
