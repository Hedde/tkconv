"""Structured JSON logging helper (copied from REFERENCE/utils/logging.py).
Keeps external dependencies minimal and produces one-line JSON objects that are
trivial to ingest in Elastic/Kibana or any log shipper.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime
from typing import Any, Dict

from fastapi import Request

DEFAULT_FIELDS = {
    "timestamp",
    "level",
    "message",
    "request_id",
    "pipeline",
    "step",
    "event",
    "duration_ms",
}

_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class JsonFormatter(logging.Formatter):
    """Very small JSON formatter (one JSON object per line)."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        for attr in (
            "request_id",
            "pipeline",
            "step",
            "event",
            "duration_ms",
        ):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)
        extra_payload = getattr(record, "extra_payload", None)
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO, stream=sys.stdout) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def get_pipeline_logger(pipeline: str, request_id: str | None = None) -> logging.Logger:
    logger = logging.getLogger(f"pipeline.{pipeline}")

    class _Adapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):  # type: ignore[override]
            kwargs.setdefault("extra", {})
            if request_id:
                kwargs["extra"]["request_id"] = request_id
            kwargs["extra"]["pipeline"] = pipeline
            return msg, kwargs

    return _Adapter(logger, {})


def new_request_id() -> str:
    return str(uuid.uuid4())


def extract_request_id(request: Request) -> str:  # type: ignore
    if "traceparent" in request.headers:
        tp = request.headers["traceparent"]
        parts = tp.split("-")
        if len(parts) >= 2 and _HEX_PATTERN.fullmatch(parts[1]):
            return parts[1]
    header_val = request.headers.get("x-request-id")
    if header_val and _ID_PATTERN.fullmatch(header_val):
        return header_val
    return new_request_id()
