"""Structured logging setup."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from vos_studio_mcp.observability.context import get_request_id, get_trace_id

SENSITIVE_KEYS = {"authorization", "api_key", "token", "secret", "password", "cookie"}


class JsonFormatter(logging.Formatter):
    """Format records as compact JSON for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            "logger": record.name,
            "trace_id": get_trace_id(),
            "request_id": get_request_id(),
        }

        extra = getattr(record, "extra", None)
        if isinstance(extra, Mapping):
            payload.update(redact_mapping(extra))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=str)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Redact known sensitive fields from structured log context."""

    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def configure_logging(level: str) -> None:
    """Configure root logging with JSON output."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
