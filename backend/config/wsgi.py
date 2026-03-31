"""
WSGI config for medical web application.
"""

import os

# Cloud Run / gunicorn: default to production unless the platform sets this explicitly.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.tracing import configure_tracing

configure_tracing()

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
