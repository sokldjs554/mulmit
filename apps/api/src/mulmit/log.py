"""Structured logging.

Every log line is a JSON object carrying the correlation context of whatever produced it — the
HTTP ``request_id``, or the ``job``/``job_id`` of a worker task — so a single incident can be
followed from API request → enqueued job → external call → notification in Cloud Logging.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

__all__ = ["bind_contextvars", "clear_contextvars", "configure_logging", "get_logger"]


def _add_severity(
    _: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    # Cloud Logging reads `severity`; keep `level` for humans.
    event_dict["severity"] = method_name.upper()
    return event_dict


def configure_logging(*, json: bool = True, level: str = "INFO", service: str = "mulmit") -> None:
    shared: list[structlog.types.Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_severity,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    bind_contextvars(service=service)

    # Route stdlib loggers (uvicorn, arq, sqlalchemy) through the same renderer.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processor=renderer)
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "anthropic._base_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
