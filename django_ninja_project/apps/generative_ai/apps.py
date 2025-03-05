from django.apps import AppConfig
from django.conf import settings


class GenerativeAIConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.generative_ai"
    verbose_name = "Generative AI"

    def ready(self):
        """Initialize services when Django starts"""
        # Import here to avoid circular imports
        from .services import gemini_service

        # Initialize the Gemini model (uses module-level singleton pattern)
        gemini_service.get_gemini_model()

        # You can also log that the service was initialized
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Gemini AI service initialized")
