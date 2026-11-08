"""Logging setup: human-readable by default, one JSON object per line when ``LOG_FORMAT=json``.

JSON logs are what log platforms (Fly, Railway, Datadog, Loki) index; ``request_id`` and any
``extra={...}`` fields are kept as top-level keys so a request can be followed across lines.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(log_format: str | None = None, level: int = logging.INFO) -> None:
    chosen = (log_format or os.getenv("LOG_FORMAT") or "text").strip().lower()
    handler = logging.StreamHandler()
    if chosen == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
