"""
WSGI config for medical web application.
"""

import os

from django.core.wsgi import get_wsgi_application

# Always default to test settings in this deployment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

# Only import settings once
application = get_wsgi_application()
