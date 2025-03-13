"""
Testing settings for the medical web application.
"""

import os
from .base import *
from google.cloud import secretmanager


# Function to access secrets from Google Secret Manager
def access_secret(project_id, secret_id, version_id="latest"):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")


# Project settings
GCP_PROJECT_ID = "medical-ai-web-app"

# Security settings - Using Google Secret Manager
SECRET_KEY = access_secret(GCP_PROJECT_ID, "test-django-secret-key")
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Database settings - Use PostgreSQL for tests
# First try to get credentials from environment variables (for CI/CD)
# If not available, fetch from Google Secret Manager
try:
    # Check if environment variables are available
    if (
        os.getenv("DB_NAME")
        and os.getenv("DB_USER")
        and os.getenv("DB_PASSWORD")
        and os.getenv("DB_HOST")
    ):
        # Use environment variables (CI/CD environment)
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.getenv("DB_NAME"),
                "USER": os.getenv("DB_USER"),
                "PASSWORD": os.getenv("DB_PASSWORD"),
                "HOST": os.getenv("DB_HOST"),
                "PORT": os.getenv("DB_PORT", "5432"),
            }
        }
    else:
        # If environment variables aren't available, use Google Secret Manager
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": access_secret(GCP_PROJECT_ID, "test-db-name"),
                "USER": access_secret(GCP_PROJECT_ID, "test-db-user"),
                "PASSWORD": access_secret(GCP_PROJECT_ID, "test-db-password"),
                "HOST": access_secret(GCP_PROJECT_ID, "test-db-host"),
                "PORT": "5432",
            }
        }
except Exception:
    # Fallback to SQLite if database connection fails
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",  # Use in-memory database as fallback
        }
    }

# Email backend for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Test-specific apps
INSTALLED_APPS += [
    "django.contrib.staticfiles.testing",
    "silk",  # Add django-silk for profiling/debugging in tests
]

# Add silk middleware
MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")

# Settings for silk in test environment
SILKY_PYTHON_PROFILER = True
SILKY_INTERCEPT_PERCENT = 100  # Intercept all requests in test environment

# Disable password hashers for faster tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
