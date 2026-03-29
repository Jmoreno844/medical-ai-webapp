"""
Legacy package entry when ``DJANGO_SETTINGS_MODULE`` is set to ``config.settings``.

**Prefer explicit modules instead:**
- ``config.settings.develop`` — local development and Docker Compose ``web``
- ``config.settings.test`` — pytest, CI, optional Docker ``test`` profile
- ``config.settings.production`` — gunicorn / Cloud Run (default in ``config.wsgi``)

This module loads **develop** for backwards compatibility.
"""

from .develop import *  # noqa: F403, F401
