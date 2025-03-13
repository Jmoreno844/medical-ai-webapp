"""
Testing settings for the medical web application.
"""

import os
import logging
import datetime
import socket
import sys
from .base import *  # noqa: F403, F401


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

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.handlers = []  # Clear any existing handlers
        root_logger.addHandler(console_handler)

        # Set appropriate log level for test environment
        root_logger.setLevel(logging.INFO)

        # Configure Django logger specifically
        django_logger = logging.getLogger("django")
        django_logger.setLevel(logging.WARNING)

        # Configure security-related loggers at appropriate levels
        security_logger = logging.getLogger("django.security")
        security_logger.setLevel(logging.INFO)

        # Quiet down noisy loggers in test environment
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
            level=logging.INFO,
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
        return response.payload.data.decode("UTF-8")
    except ImportError:
        logging.warning("Google Secret Manager not available, using default values")
        return default
    except Exception as e:
        logging.warning(f"Failed to access secret {secret_id}: {str(e)}")
        return default


# Project settings
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

# Security settings - Using Google Secret Manager with fallback
# Generate a fallback secret key for testing if Secret Manager is unavailable
FALLBACK_SECRET_KEY = os.environ.get(
    "DJANGO_FALLBACK_SECRET_KEY",
    "django-insecure-test-key-do-not-use-in-production-environments",
)
SECRET_KEY = access_secret(
    GCP_PROJECT_ID, "django_secret_key", default=FALLBACK_SECRET_KEY
)
DEBUG = False

# In your Django settings
ALLOWED_HOSTS = [
    ".run.app",  # Allows Cloud Run URLs
    "your-internal-lb.com",  # If you use an internal load balancer
    "localhost",
    "127.0.0.1",  # For local development
]

# Database settings - Use PostgreSQL for tests
# First try to get credentials from environment variables (for CI/CD)
# If not available, fetch from Google Secret Manager with SQLite fallback
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
        logging.info("Using database configuration from environment variables")
    else:
        # If environment variables aren't available, use Google Secret Manager with fallbacks
        db_name = access_secret(
            GCP_PROJECT_ID, "db_name", default=os.getenv("DB_NAME", "test_db")
        )
        db_user = access_secret(
            GCP_PROJECT_ID, "db_user", default=os.getenv("DB_USER", "test_user")
        )
        db_password = access_secret(
            GCP_PROJECT_ID, "db_password", default=os.getenv("DB_PASSWORD", "")
        )
        db_host = access_secret(
            GCP_PROJECT_ID, "db_host", default=os.getenv("DB_HOST", "localhost")
        )

        # Only use PostgreSQL if we have valid credentials
        if db_name and db_user and db_password and db_host:
            DATABASES = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": db_name,
                    "USER": db_user,
                    "PASSWORD": db_password,
                    "HOST": db_host,
                    "PORT": "5432",
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
    MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")  # noqa: F405

    # Settings for silk in test environment
    SILKY_PYTHON_PROFILER = True
    SILKY_INTERCEPT_PERCENT = 100  # Intercept all requests in test environment

# Disable password hashers for faster tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.run.app",  # Trust all Cloud Run domains
]
# Security settings
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Log successful initialization
logging.info("Test settings loaded successfully")
