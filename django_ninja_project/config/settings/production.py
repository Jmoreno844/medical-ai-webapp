"""
Production settings for the medical web application.
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
GCP_PROJECT_ID = "your-gcp-project-id"  # Set this to your actual GCP project ID

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = access_secret(GCP_PROJECT_ID, "django-secret-key-prod")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Update this with your actual domain
ALLOWED_HOSTS = [access_secret(GCP_PROJECT_ID, "allowed-hosts").split(",")]

# Database configuration
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": access_secret(GCP_PROJECT_ID, "db-name"),
        "USER": access_secret(GCP_PROJECT_ID, "db-user"),
        "PASSWORD": access_secret(GCP_PROJECT_ID, "db-password"),
        "HOST": access_secret(GCP_PROJECT_ID, "db-host"),
        "PORT": access_secret(GCP_PROJECT_ID, "db-port"),
        "OPTIONS": {"sslmode": "require"},
    }
}

# Production-specific apps and middleware
INSTALLED_APPS += [
    # Add production-specific apps here
]

MIDDLEWARE += [
    # Add production-specific middleware here
]

# Static files settings
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"

# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
MEDIA_URL = "/media/"

# Email configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = access_secret(GCP_PROJECT_ID, "email-host")
EMAIL_PORT = int(access_secret(GCP_PROJECT_ID, "email-port"))
EMAIL_HOST_USER = access_secret(GCP_PROJECT_ID, "email-user")
EMAIL_HOST_PASSWORD = access_secret(GCP_PROJECT_ID, "email-password")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = access_secret(GCP_PROJECT_ID, "default-from-email")

# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
