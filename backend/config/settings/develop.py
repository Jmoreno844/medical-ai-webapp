"""
Development settings for the medical web application.
"""

import os
import warnings
from .base import *  # noqa: F403, F401
from .logging_utils import build_console_logging
from dotenv import load_dotenv

load_dotenv()

ENVIRONMENT = "dev"
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = (
    os.environ.get("DJANGO_SECRET_KEY")
    or os.environ.get("SECRET_KEY")
    or "django-insecure-development-key-change-this"
)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "not-loaded")


GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "not-loaded")
GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT = os.environ.get(
    "GCP_STORAGE_IMPERSONATED_SERVICE_ACCOUNT", "not-loaded"
)
GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH = os.environ.get(
    "GCP_STORAGE_SERVICE_ACCOUNT_KEY_PATH", "not-loaded"
)
TRANSCRIPTION_CLOUD_FUNCTION_URL = os.environ.get(
    "TRANSCRIPTION_CLOUD_FUNCTION_URL", "not-loaded"
)
# Accept either env name (historical typo: BASE_URL vs full setting name)
GENERATE_DOCUMENT_CLOUD_FUNCTION_URL = os.environ.get(
    "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL",
    os.environ.get("GENERATE_DOCUMENT_CLOUD_FUNCTION_BASE_URL", "not-loaded"),
)
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DEBUG", default=True)

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Add Vite development server
    "http://127.0.0.1:5173",  # Also add the IP version
]


# Additional CORS settings to ensure proper functioning
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "cookie",  # Add cookie to allowed headers
    "traceparent",
    "tracestate",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
# Add django-silk for profiling/debugging
INSTALLED_APPS += ["silk"]  # noqa: F405
MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")  # noqa: F405

# Settings for silk
SILKY_PYTHON_PROFILER = True
SILKY_AUTHENTICATION = True  # User must login
SILKY_AUTHORISATION = True  # User must have permissions
SILKY_META = True
INTERNAL_IPS = ["127.0.0.1"]

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "not_env_db"),
        "USER": os.getenv("DB_USER", "not_env_user"),
        "PASSWORD": os.getenv("DB_PASSWORD", "not_env_oassword"),
        "HOST": os.getenv("DB_HOST", "not_env_host"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable security settings that might interfere with development
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = "Lax"  # Required for cross-site requests with credentials
CSRF_USE_SESSIONS = False  # Store CSRF token in cookie instead of session

SESSION_COOKIE_SECURE = False  # Keep True for HTTPS, even in development
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
SESSION_COOKIE_SAMESITE = "Lax"  # Required for cross-site requests with credentials
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Session ends when browser closes
SESSION_COOKIE_AGE = 3600  # 1 hour in seconds
# Replace the existing LOGGING dictionary with this more comprehensive one:

"""
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": os.path.join(BASE_DIR, "logs/django-debug.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Root logger
        "": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        # Django's loggers
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django.contrib.auth": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Your app loggers - add all relevant modules
        "apps.documentos.api.callbacks": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "apps.documentos.api.generation": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "apps.documentos.api.sse": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "utils.auth": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "apps.users.api": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },info 
}

"""

LOGGING = build_console_logging("DEBUG" if DEBUG else "INFO")
