"""
WSGI config for medical web application.
"""

import os
import logging
from config.cors_wrapper import CORSMiddlewareWrapper
from django.core.wsgi import get_wsgi_application

# Always default to test settings in this deployment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

# Only import settings once
base_application = get_wsgi_application()

application = CORSMiddlewareWrapper(base_application)

logging.warning("WSGI application initialized with CORS wrapper")
