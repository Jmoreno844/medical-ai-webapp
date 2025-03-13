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

# Add django-silk for profiling/debugging
INSTALLED_APPS += ["silk"]
MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")

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
SESSION_COOKIE_SECURE = False
