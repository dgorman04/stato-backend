"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.
HTTP only; real-time is handled by the separate Node WebSocket server.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

application = get_asgi_application()
