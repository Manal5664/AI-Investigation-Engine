"""Structured application logging.

Configures the ``app`` logger namespace so request and error logs carry useful
metadata without touching uvicorn's own loggers. ``LOG_JSON=true`` emits
single-line JSON records suitable for production log aggregation; the default
human-readable formatter keeps local development familiar.

Loggers inside the ``app`` namespace propagate to the ``app`` logger, which is
configured here with a single stream handler. Nothing sensitive is logged:
access records carry only method, path, status, duration, and request ID.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

APP_LOGGER_NAME = "app"


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with an optional ``extra_fields`` dict."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Apply the app-namespace logging configuration for the current settings."""
    level_name = settings.LOG_LEVEL.strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(level)
    app_logger.propagate = False
    app_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"
            )
        )
    app_logger.addHandler(handler)


__all__ = ["JsonFormatter", "configure_logging"]
