"""
WSGI config for medical web application.
"""

import os

from django.core.wsgi import get_wsgi_application

# Cloud Run / gunicorn: default to production unless the platform sets this explicitly.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Only import settings once
application = get_wsgi_application()
