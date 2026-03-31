"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.tracing import configure_tracing

configure_tracing()

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
