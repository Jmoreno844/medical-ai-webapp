"""
Development settings for the medical web application.
"""

import os
import warnings
from .base import *
from dotenv import load_dotenv

load_dotenv()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-development-key-change-this"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Conditionally add django-debug-toolbar if installed
try:
    import debug_toolbar

    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    warnings.warn(
        "django-debug-toolbar not installed. "
        "Install it with: pip install django-debug-toolbar"
    )

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
SESSION_COOKIE_SECURE = False
