"""Lightweight ASGI middleware for request correlation, security headers, and
access logging.

- Accepts a safe incoming ``X-Request-ID`` (validated and length-capped) or
  generates one, returns it on every response, stores it on ``scope["state"]``
  so request handlers can read ``request.state.request_id``, and includes it in
  access logs.
- Adds conservative HTTP security headers. The Content-Security-Policy keeps the
  existing CDN-based frontend working (jsDelivr scripts, Google Fonts, and
  inline styles/scripts); the ``'unsafe-inline'`` directive is a documented
  trade-off for this phase.
- Emits a structured access log per HTTP request (method, path, status,
  duration, request ID). No query strings, bodies, API keys, or authorization
  values are logged.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders

ACCESS_LOGGER = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "connect-src 'self'; "
        "font-src 'self' data: https://fonts.gstatic.com "
        "https://cdn.jsdelivr.net; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
        "https://cdn.jsdelivr.net"
    ),
}


def extract_request_id(headers: list[tuple[bytes, bytes]]) -> str:
    """Return a validated incoming request ID or generate a fresh one."""
    for name, value in headers:
        if name.lower() != b"x-request-id":
            continue
        raw = value.decode("latin-1", errors="replace").strip()
        if (
            raw
            and len(raw) <= MAX_REQUEST_ID_LENGTH
            and _SAFE_REQUEST_ID_RE.match(raw) is not None
        ):
            return raw
        break
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """ASGI middleware that decorates every HTTP response."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return

        request_id = extract_request_id(scope.get("headers", []))
        scope.setdefault("state", {})["request_id"] = request_id
        start_time = time.perf_counter()
        status_holder: dict[str, int] = {"status": 500}

        async def send_with_context(message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = MutableHeaders(raw=message["headers"])
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                message["headers"] = headers.raw
            await send(message)

        try:
            await self.inner(scope, receive, send_with_context)
        except Exception:
            ACCESS_LOGGER.exception(
                "request_failed",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": scope.get("method", ""),
                        "path": scope.get("path", ""),
                    }
                },
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            ACCESS_LOGGER.info(
                "request_completed",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": scope.get("method", ""),
                        "path": scope.get("path", ""),
                        "status": status_holder["status"],
                        "duration_ms": round(duration_ms, 2),
                    }
                },
            )


__all__ = [
    "MAX_REQUEST_ID_LENGTH",
    "REQUEST_ID_HEADER",
    "RequestContextMiddleware",
    "SECURITY_HEADERS",
    "extract_request_id",
]
