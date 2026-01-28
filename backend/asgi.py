"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import stato.routing  # 👈 we'll create this file in the next step

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Standard Django ASGI app for HTTP
django_asgi_app = get_asgi_application()

# Main ASGI application with HTTP + WebSocket support
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(
                stato.routing.websocket_urlpatterns
            )
        ),
    }
)
