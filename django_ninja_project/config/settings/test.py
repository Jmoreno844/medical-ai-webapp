"""
Testing settings for the medical web application.
"""

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

# Security settings
SECRET_KEY = access_secret(GCP_PROJECT_ID, "django-secret-key-test")
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Database - Use SQLite for tests for speed
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",  # Use in-memory database for tests
    }
}

# Email backend for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Test-specific apps
INSTALLED_APPS += ["django.contrib.staticfiles.testing"]

# Disable password hashers for faster tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
