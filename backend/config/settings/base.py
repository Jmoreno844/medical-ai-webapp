"""
Base Django settings for the medical web application.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
_settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
if _settings_module:
    logger.debug("Loading Django settings module: %s", _settings_module)
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
INSTALLED_APPS = [
    "corsheaders",  # Added corsheaders app
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "ninja",
    # Local apps
    "apps.core.apps.CoreConfig",  # Using proper AppConfig class
    "apps.users.apps.UsersConfig",
    "apps.encuentro.apps.EncuentroConfig",
    "apps.pacientes.apps.PacientesConfig",
    "apps.plantillas.apps.PlantillasConfig",
    "apps.documentos.apps.DocumentosConfig",
    "apps.generative_ai.apps.GenerativeAIConfig",
]

# Custom user model
AUTH_USER_MODEL = "users.User"

# CORS Settings removed

MIDDLEWARE = [
    # "apps.core.middleware.DebugCorsMiddleware",  # Debug CORS middleware comes first
    "middlewares.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # CORS middleware comes second
    "django.middleware.common.CommonMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# Default to SQLite, will be overridden in environment-specific settings
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security settings
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

LOGIN_URL = "/admin/login/"  # Redirect to the admin login page instead
CSRF_COOKIE_NAME = "_xsrf"
