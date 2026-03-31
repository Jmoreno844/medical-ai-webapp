"""
Testing settings for the medical web application.
"""

import os

os.environ.setdefault("OTEL_SDK_DISABLED", "1")
import logging
import datetime
import socket
import sys
import json
from .base import *  # noqa: F403, F401

globals().pop("LOGGING", None)

# Initialize logging configuration first to capture any startup errors
def configure_json_logging():
    """
    Configure structured JSON logging suitable for Google Cloud environments.
    Implements security best practices by filtering sensitive information.
    """
    try:
        from pythonjsonlogger import jsonlogger

        # Create log formatter with additional contextual information
        class CustomJsonFormatter(jsonlogger.JsonFormatter):
            """Enhanced JSON formatter with additional fields for observability."""

            def add_fields(self, log_record, record, message_dict):
                super(CustomJsonFormatter, self).add_fields(
                    log_record, record, message_dict
                )

                # Add timestamp in ISO format
                now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                log_record["timestamp"] = now

                # Add host information
                log_record["host"] = socket.gethostname()

                # Add environment marker
                log_record["environment"] = "test"

                # Ensure consistent severity field for GCP
                log_record["severity"] = record.levelname

                # Add trace information if available (for GCP trace integration)
                trace_id = getattr(record, "trace_id", None)
                if trace_id:
                    log_record["logging.googleapis.com/trace"] = trace_id

        # Create console handler that outputs to stderr
        console_handler = logging.StreamHandler(sys.stderr)

        # Define formatter with specifically included fields to avoid leaking sensitive data
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(severity)s %(name)s %(message)s %(pathname)s %(lineno)s"
            " %(funcName)s %(host)s %(environment)s"
        )

        console_handler.setFormatter(formatter)

        # Configure root logger to show EVERYTHING
        root_logger = logging.getLogger()
        root_logger.handlers = []  # Clear any existing handlers
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.DEBUG)  # Set to DEBUG level

        # Configure Django logger specifically
        django_logger = logging.getLogger("django")
        django_logger.setLevel(logging.INFO)  # Change to INFO to see more details

        # Configure Django CORS middleware logger to show INFO logs
        django_cors_logger = logging.getLogger("corsheaders")
        django_cors_logger.setLevel(logging.DEBUG)

        # Configure CORS debug middleware logger - set to DEBUG
        cors_debug_logger = logging.getLogger("apps.core.middleware")
        cors_debug_logger.setLevel(logging.DEBUG)  # Set to DEBUG level

        # Configure security-related loggers at appropriate levels
        security_logger = logging.getLogger("django.security")
        security_logger.setLevel(logging.INFO)
        logging.getLogger("silk").setLevel(logging.WARNING)

        # Setup log filter to prevent sensitive data leakage
        class SensitiveDataFilter(logging.Filter):
            """Filter to redact potentially sensitive information from logs."""

            def filter(self, record):
                # List of patterns to redact
                sensitive_terms = ["password", "secret", "token", "key", "auth"]

                # Check if message contains sensitive data and redact if needed
                if hasattr(record, "msg") and isinstance(record.msg, str):
                    message = record.msg.lower()
                    for term in sensitive_terms:
                        if term in message:
                            # Add a warning about potential sensitive data
                            record.msg = f"[REDACTED SENSITIVE DATA] {record.module}.{record.funcName}"
                            break

                return True

        # Apply sensitive data filter to root logger
        sensitive_filter = SensitiveDataFilter()
        for handler in root_logger.handlers:
            handler.addFilter(sensitive_filter)

        logging.info("JSON logging configured for test environment")
    except Exception as e:
        # Fallback to basic logging if JSON logging fails
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )
        logging.warning(f"Failed to configure JSON logging, using basic logging: {e}")


# Initialize logging configuration before anything else
configure_json_logging()


# Function to safely access secrets from Google Secret Manager with proper fallbacks
def access_secret(project_id, secret_id, version_id="latest", default=None):
    """
    Access a secret from Google Secret Manager with fallback to default value.

    Args:
        project_id: GCP project ID
        secret_id: Secret identifier
        version_id: Version of secret (default: latest)
        default: Default value to use if secret access fails

    Returns:
        Secret value or default if access fails
    """
    # Return default immediately if project_id is not set
    if not project_id:
        logging.warning(f"No GCP_PROJECT_ID set, using default for {secret_id}")
        return default

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(name=name)
        raw = response.payload.data.decode("UTF-8")
        return raw.strip() if isinstance(raw, str) else default
    except ImportError:
        logging.warning("Google Secret Manager not available, using default values")
        return default
    except Exception as e:
        logging.warning(f"Failed to access secret {secret_id}: {str(e)}")
        return default


def _env_strip(key: str) -> str | None:
    value = os.getenv(key)
    return value.strip() if value else None


ENVIRONMENT = "test"

# Project settings
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "not-loaded")

# Security settings - Using Google Secret Manager with fallback
# Generate a fallback secret key for testing if Secret Manager is unavailable
FALLBACK_SECRET_KEY = os.environ.get(
    "DJANGO_FALLBACK_SECRET_KEY",
    "django-insecure-test-key-do-not-use-in-production-environments",
)
# Cloud Run (Terraform) maps secrets to SECRET_KEY / JWT_SECRET; IDs must match Secret Manager.
SECRET_KEY = _env_strip("SECRET_KEY") or access_secret(
    GCP_PROJECT_ID, "django-secret-key", default=FALLBACK_SECRET_KEY
)
JWT_SECRET_KEY = _env_strip("JWT_SECRET") or access_secret(
    GCP_PROJECT_ID, "jwt-secret-key", default="not-loaded"
)
SERVICE_ACCOUNT_JSON = access_secret(
    GCP_PROJECT_ID, "service-account-json", default="{}"
)

TRANSCRIPTION_CLOUD_FUNCTION_URL = os.environ.get(
    "TRANSCRIPTION_CLOUD_FUNCTION_URL", "not-loaded"
)
GENERATE_DOCUMENT_CLOUD_FUNCTION_URL = os.environ.get(
    "GENERATE_DOCUMENT_CLOUD_FUNCTION_URL", "not-loaded"
)
# Change to DEBUG mode to help diagnose issues
DEBUG = True

# In your Django settings
ALLOWED_HOSTS = ["*"]

def _postgres_options_for_host(host: str) -> dict:
    """Cloud SQL Unix socket under /cloudsql/ does not use TLS like a public IP."""
    if host.startswith("/cloudsql/"):
        return {}
    return {"sslmode": "require"}


def _resolve_db_host() -> str | None:
    explicit = _env_strip("DB_HOST")
    if explicit:
        return explicit
    conn = _env_strip("INSTANCE_CONNECTION_NAME")
    if conn:
        return f"/cloudsql/{conn}"
    return None


# Database settings - Use PostgreSQL for tests
# First try to get credentials from environment variables (for CI/CD)
# If not available, fetch from Google Secret Manager with SQLite fallback
try:
    db_host = _resolve_db_host()
    db_name_env = _env_strip("DB_NAME")
    db_user_env = _env_strip("DB_USER")
    db_password_env = _env_strip("DB_PASSWORD")
    if db_name_env and db_user_env and db_password_env and db_host:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": db_name_env,
                "USER": db_user_env,
                "PASSWORD": db_password_env,
                "HOST": db_host,
                "PORT": (
                    ""
                    if db_host.startswith("/cloudsql/")
                    else os.getenv("DB_PORT", "5432")
                ),
                "OPTIONS": _postgres_options_for_host(db_host),
            }
        }
        logging.info("Using database configuration from environment variables")
    else:
        db_name = access_secret(
            GCP_PROJECT_ID, "db-name", default=os.getenv("DB_NAME", "test_db")
        )
        db_user = access_secret(
            GCP_PROJECT_ID, "db-user", default=os.getenv("DB_USER", "test_user")
        )
        db_password = access_secret(
            GCP_PROJECT_ID, "db-password", default=os.getenv("DB_PASSWORD", "")
        )
        db_host = _resolve_db_host() or access_secret(
            GCP_PROJECT_ID,
            "db-host",
            default=os.getenv("DB_HOST", "localhost"),
        )

        if db_name and db_user and db_password and db_host:
            DATABASES = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": db_name,
                    "USER": db_user,
                    "PASSWORD": db_password,
                    "HOST": db_host,
                    "PORT": (
                        "" if db_host.startswith("/cloudsql/") else "5432"
                    ),
                    "OPTIONS": _postgres_options_for_host(db_host),
                }
            }
            logging.info("Using database configuration from Google Secret Manager")
        else:
            raise ValueError("Incomplete database credentials")
except Exception as e:
    # Fallback to SQLite if database connection fails
    logging.warning(f"Failed to configure PostgreSQL: {e}, falling back to SQLite")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",  # Use in-memory database as fallback
        }
    }
    logging.info("Using in-memory SQLite database as fallback")

# Email backend for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Test-specific apps
INSTALLED_APPS += ["django.contrib.staticfiles.testing"]  # noqa: F405

# Add silk for profiling/debugging in tests if not already added
if "silk" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS += ["silk"]  # noqa: F405
    try:
        anchor = "corsheaders.middleware.CorsMiddleware"
        idx = MIDDLEWARE.index(anchor)  # noqa: F405
        MIDDLEWARE.insert(idx + 1, "silk.middleware.SilkyMiddleware")  # noqa: F405
    except ValueError:
        MIDDLEWARE.append("silk.middleware.SilkyMiddleware")  # noqa: F405
    # Settings for silk in test environment
    SILKY_PYTHON_PROFILER = True
    SILKY_INTERCEPT_PERCENT = 100  # Intercept all requests in test environment

# Add CORS skip middleware configuration
# Define trusted origins that can bypass CORS restrictions during testing


# Disable password hashers for faster tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Security settings
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"  # Required for cross-site requests
CSRF_USE_SESSIONS = False  # Use cookies, not sessions

SESSION_COOKIE_SECURE = True  # Keep this True for security
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to cookies
SESSION_COOKIE_SAMESITE = "None"  # Try changing to None for cross-domain
# SESSION_COOKIE_DOMAIN = None  # Commented out as requested
SESSION_COOKIE_NAME = "medwebapp_session"
SESSION_COOKIE_AGE = 3600  # 1 hour (matches your session.set_expiry)
# CORS settings – making more specific and aligned with develop.py
CORS_ALLOW_ALL_ORIGINS = False  # More secure approach, only allow specific origins

# Keep the specific origins with Cloud Run URL as the primary focus
CORS_ALLOWED_ORIGINS = ["https://medapp.sebastianmoreno.lat"]
# Make sure credentials are allowed
CORS_ALLOW_CREDENTIALS = True

# Be explicit about allowed methods
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# Define specific allowed headers instead of allowing all
CORS_ALLOW_ALL_HEADERS = False
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
    "cookie",  # Added this!
    "traceparent",
    "tracestate",
]

# Expose headers that the frontend might need
CORS_EXPOSE_HEADERS = ["Content-Type", "X-CSRFToken", "Authorization"]

# Set a reasonable preflight max age
CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours

# Update CSRF trusted origins to explicitly include the Cloud Run URL
CSRF_TRUSTED_ORIGINS = ["https://medapp.sebastianmoreno.lat"]

# Make sure logging is configured to capture CORS-related messages
logging.getLogger("apps.core.middleware").setLevel(logging.DEBUG)

# Log successful initialization
logging.info("Test settings loaded successfully")
