"""
Production settings for the medical web application.

Set ``DJANGO_SECRET_KEY``, ``JWT_SECRET_KEY``, database ``DB_*``, GCS and Cloud
Function URLs via environment or your platform’s secret injection (see
``documentation/secrets_and_environments.md``).
"""

import os
from .base import *  # noqa: F403, F401

ENVIRONMENT = "production"

# Security settings
DEBUG = False
ALLOWED_HOSTS = ["*"]  # Update with your domain in production

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY must be set in production")

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY must be set in production")

GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH = os.environ.get(
    "GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH", ""
)
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON", "{}")

TRANSCRIPTION_CLOUD_FUNCTION_URL = os.environ.get(
    "TRANSCRIPTION_CLOUD_FUNCTION_URL", ""
)
GENERATE_DOCUMENT_CLOUD_FUNCTION_URL = os.environ.get(
    "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL",
    os.environ.get("GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL", ""),
)

# Database settings
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME"),
        "USER": os.environ.get("DB_USER"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Production email backend
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Silk configuration (if needed in production)
if os.environ.get("ENABLE_SILK", "False").lower() == "true":
    INSTALLED_APPS += ["silk"]  # noqa: F405
    MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")  # noqa: F405

# Static files settings
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")  # noqa: F405
STATIC_URL = "/static/"

# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, "media")  # noqa: F405
MEDIA_URL = "/media/"

# Email configuration
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL")
