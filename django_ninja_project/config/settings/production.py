"""
Production settings for the medical web application.
"""

import os
from .base import *  # Import only from base, not from develop or test

# Security settings
DEBUG = False
ALLOWED_HOSTS = ["*"]  # Update with your domain in production

# Get the secret key from environment variable
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

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
    INSTALLED_APPS += ["silk"]
    MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")

# Static files settings
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"

# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/media/"

# Email configuration
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT"))
EMAIL_HOST_USER = os.environ.get("EMAIL_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL")
