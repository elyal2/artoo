from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any

from .config import settings


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003 - match logging API
        payload: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.__dict__:
            extra = {
                k: v
                for k, v in record.__dict__.items()
                if k
                not in {
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                }
            }
            payload.update(extra)
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO), handlers=[handler]
    )


__all__ = ["configure_logging"]
