"""
Structured JSON logging with per-request correlation IDs.

Every record is emitted as one JSON object per line with the fields
``ts``, ``level``, ``logger``, ``msg`` and ``request_id`` (plus ``exc`` when an
exception is attached). The request ID is carried in a ContextVar that the API
middleware sets for the lifetime of each request; it propagates into worker
threads started with ``asyncio.to_thread`` / ``run_in_threadpool``.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger and on uvicorn's loggers.

    Safe to call more than once (the handler is replaced, not duplicated).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    handler.set_name("rm-json")

    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if h.get_name() != "rm-json"]
    # Drop basicConfig-style plain handlers so nothing is logged twice in
    # non-JSON form; keep foreign handlers (e.g. pytest's capture handler).
    root.handlers = [h for h in root.handlers if type(h) is not logging.StreamHandler]
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
    # The API middleware already logs one line per request with status and
    # latency, so uvicorn's access log would only duplicate it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
