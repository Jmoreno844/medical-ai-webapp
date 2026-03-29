from django.apps import AppConfig
from django.conf import settings


class GenerativeAIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.generative_ai"
    verbose_name = "Generative AI"
