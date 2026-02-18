"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.http import JsonResponse, HttpResponse
import os
import re

def root_view(request):
    """Respond to GET / so WebSocket clients hitting the wrong server get a clear response."""
    return JsonResponse({
        "message": "SportsHub API",
        "api": "/api/",
        "note": "WebSockets use the Node server (e.g. ws://localhost:3001), not this URL.",
    })

def _add_cors_headers(request, response):
    """Add CORS headers so cross-origin frontends can use this response."""
    origin = request.META.get("HTTP_ORIGIN", "*")
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Expose-Headers"] = "Accept-Ranges, Content-Length, Content-Range"


def _serve_media_with_ranges(request, path):
    """Serve file from MEDIA_ROOT with Accept-Ranges so video seeking works in the browser."""
    path = (path or "").lstrip("/")
    if not path:
        r = HttpResponse(status=404)
        _add_cors_headers(request, r)
        return r
    media_root = os.path.abspath(str(settings.MEDIA_ROOT))
    file_path = os.path.normpath(os.path.join(media_root, path))
    if not file_path.startswith(media_root) or not os.path.isfile(file_path):
        r = HttpResponse(status=404)
        _add_cors_headers(request, r)
        return r
    size = os.path.getsize(file_path)
    content_type = "application/octet-stream"
    if path.lower().endswith(".mp4"):
        content_type = "video/mp4"
    elif path.lower().endswith(".webm"):
        content_type = "video/webm"
    range_header = request.META.get("HTTP_RANGE")
    if not range_header:
        with open(file_path, "rb") as f:
            content = f.read()
        response = HttpResponse(content, status=200, content_type=content_type)
        response["Content-Length"] = str(size)
        response["Accept-Ranges"] = "bytes"
        _add_cors_headers(request, response)
        return response
    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        r = HttpResponse(status=416)
        _add_cors_headers(request, r)
        return r
    start_s, end_s = match.groups()
    start = int(start_s) if start_s else 0
    end = int(end_s) if end_s else size - 1
    if start >= size:
        r = HttpResponse(status=416)
        _add_cors_headers(request, r)
        return r
    end = min(end, size - 1)
    length = end - start + 1
    with open(file_path, "rb") as f:
        f.seek(start)
        content = f.read(length)
    response = HttpResponse(content, status=206, content_type=content_type)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    _add_cors_headers(request, response)
    return response

urlpatterns = [
    path("", root_view),
    path("admin/", admin.site.urls),
    path("api/", include("stato.urls")),
    path("media/<path:path>", _serve_media_with_ranges),
]
