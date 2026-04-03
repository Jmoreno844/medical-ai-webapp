"""
Staging settings for the medical web application.
"""

from __future__ import annotations

import datetime
import logging
import os
import socket
import sys

from .base import *  # noqa: F403, F401

globals().pop("LOGGING", None)


def configure_json_logging() -> None:
    """Configure structured logs with Cloud Trace correlation fields."""
    try:
        from pythonjsonlogger import jsonlogger

        class CustomJsonFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)

                now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                log_record["timestamp"] = now
                log_record["host"] = socket.gethostname()
                log_record["environment"] = "stg"
                log_record["severity"] = record.levelname

                google_cloud_trace = getattr(record, "google_cloud_trace", None)
                trace_id = getattr(record, "trace_id", None)
                span_id = getattr(record, "span_id", None)
                project = (
                    os.getenv("GOOGLE_CLOUD_PROJECT")
                    or os.getenv("GCP_PROJECT")
                    or os.getenv("GCP_PROJECT_ID")
                )

                if google_cloud_trace and google_cloud_trace != "-":
                    log_record["logging.googleapis.com/trace"] = google_cloud_trace
                elif trace_id and trace_id != "-" and project:
                    log_record["logging.googleapis.com/trace"] = (
                        f"projects/{project}/traces/{trace_id}"
                    )

                if span_id and span_id != "-":
                    log_record["logging.googleapis.com/spanId"] = span_id

        console_handler = logging.StreamHandler(sys.stderr)
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(severity)s %(name)s %(message)s %(pathname)s %(lineno)s"
            " %(funcName)s %(host)s %(environment)s"
        )
        console_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.INFO)

        logging.getLogger("django").setLevel(logging.INFO)
        logging.getLogger("corsheaders").setLevel(logging.INFO)
        logging.getLogger("apps.core.middleware").setLevel(logging.INFO)
        logging.getLogger("django.security").setLevel(logging.INFO)
        logging.getLogger("silk").setLevel(logging.WARNING)

        logging.info("JSON logging configured for staging environment")
    except Exception as exc:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )
        logging.warning(
            "Failed to configure JSON logging, using basic logging: %s", exc
        )


configure_json_logging()


def access_secret(project_id, secret_id, version_id="latest", default=None):
    """Access a secret from Google Secret Manager with a safe fallback."""
    if not project_id:
        logging.warning("No GCP project set, using default for %s", secret_id)
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
    except Exception as exc:
        logging.warning("Failed to access secret %s: %s", secret_id, exc)
        return default


def _env_strip(key: str) -> str | None:
    value = os.getenv(key)
    return value.strip() if value else None


ENVIRONMENT = "stg"
GCP_PROJECT_ID = (
    os.environ.get("GCP_PROJECT_ID")
    or os.environ.get("GCP_PROJECT")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
)
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "not-loaded")

FALLBACK_SECRET_KEY = os.environ.get(
    "DJANGO_FALLBACK_SECRET_KEY",
    "django-insecure-stg-key-do-not-use-in-production",
)
SECRET_KEY = (
    _env_strip("SECRET_KEY")
    or _env_strip("DJANGO_SECRET_KEY")
    or access_secret(GCP_PROJECT_ID, "django-secret-key", default=FALLBACK_SECRET_KEY)
)
JWT_SECRET_KEY = (
    _env_strip("JWT_SECRET")
    or _env_strip("JWT_SECRET_KEY")
    or access_secret(GCP_PROJECT_ID, "jwt-secret-key", default="not-loaded")
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
COPILOT_AGENT_BASE_URL = os.environ.get(
    "COPILOT_AGENT_BASE_URL",
    "not-loaded",
)
COPILOT_SERVICE_SHARED_JWT = _env_strip("COPILOT_SERVICE_SHARED_JWT") or access_secret(
    GCP_PROJECT_ID,
    "copilot-service-shared-jwt",
    default="not-loaded",
)
COPILOT_AGENT_AUDIENCE = os.environ.get(
    "COPILOT_AGENT_AUDIENCE",
    "app-api-service",
)
COPILOT_AGENT_TIMEOUT_SECONDS = float(
    os.environ.get("COPILOT_AGENT_TIMEOUT_SECONDS", "60")
)
CLOUD_TASKS_REGION = os.environ.get("CLOUD_TASKS_REGION", "not-loaded")
TRANSCRIPTION_QUEUE_NAME = os.environ.get("TRANSCRIPTION_QUEUE_NAME", "not-loaded")
CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT = os.environ.get(
    "CLOUD_TASKS_INVOKER_SERVICE_ACCOUNT", "not-loaded"
)

DEBUG = False
ALLOWED_HOSTS = ["*"]


def _postgres_options_for_host(host: str) -> dict:
    if host.startswith("/cloudsql/") or host in {"127.0.0.1", "localhost"}:
        return {}
    return {"sslmode": "require"}


def _resolve_db_host() -> str | None:
    explicit = _env_strip("DB_HOST")
    if explicit:
        return explicit
    return None


def _normalize_db_user(user: str | None) -> str | None:
    if not user:
        return None
    return user.removesuffix(".gserviceaccount.com")


db_host = _resolve_db_host()
db_name = _env_strip("DB_NAME")
db_user = _normalize_db_user(_env_strip("DB_USER"))
db_password = _env_strip("DB_PASSWORD")
db_port = _env_strip("DB_PORT") or "5432"
conn_max_age = int(_env_strip("CONN_MAX_AGE") or "300")

if not (db_name and db_user and db_host):
    raise ValueError("Incomplete staging database configuration")

database_config = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": db_name,
    "USER": db_user,
    "HOST": db_host,
    "PORT": db_port,
    "OPTIONS": _postgres_options_for_host(db_host),
    "CONN_MAX_AGE": conn_max_age,
    "CONN_HEALTH_CHECKS": True,
}

if db_password:
    database_config["PASSWORD"] = db_password

DATABASES = {"default": database_config}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if os.environ.get("ENABLE_SILK", "false").lower() == "true":
    if "silk" not in INSTALLED_APPS:  # noqa: F405
        INSTALLED_APPS += ["silk"]  # noqa: F405
    try:
        anchor = "corsheaders.middleware.CorsMiddleware"
        idx = MIDDLEWARE.index(anchor)  # noqa: F405
        if "silk.middleware.SilkyMiddleware" not in MIDDLEWARE:  # noqa: F405
            MIDDLEWARE.insert(idx + 1, "silk.middleware.SilkyMiddleware")  # noqa: F405
    except ValueError:
        if "silk.middleware.SilkyMiddleware" not in MIDDLEWARE:  # noqa: F405
            MIDDLEWARE.append("silk.middleware.SilkyMiddleware")  # noqa: F405

    SILKY_PYTHON_PROFILER = True
    SILKY_INTERCEPT_PERCENT = 100

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"
CSRF_USE_SESSIONS = False

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_NAME = "medwebapp_session"
SESSION_COOKIE_AGE = 3600

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = ["https://medapp.sebastianmoreno.lat"]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
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
    "cookie",
    "traceparent",
    "tracestate",
]
CORS_EXPOSE_HEADERS = ["Content-Type", "X-CSRFToken", "Authorization"]
CORS_PREFLIGHT_MAX_AGE = 86400
CSRF_TRUSTED_ORIGINS = ["https://medapp.sebastianmoreno.lat"]

logging.info("Staging settings loaded successfully")
