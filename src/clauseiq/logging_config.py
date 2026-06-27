"""Structured logging via structlog.

Every log line is a structured event (JSON in production, pretty colours in
dev) carrying a ``trace_id`` so a single contract analysis can be followed
across the supervisor and all worker agents. ``print()`` is never used anywhere
in ``src/``.

Usage::

    from clauseiq.logging_config import configure_logging, get_logger, trace_context

    configure_logging()                      # once, at process start
    log = get_logger(__name__)

    with trace_context() as trace_id:
        log.info("analyzing_clause", clause_id="cl1")   # trace_id auto-attached
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import structlog
from structlog.types import EventDict, WrappedLogger

from clauseiq.config import settings

# The current trace id, propagated implicitly across async tasks via contextvars.
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

_configured = False


def _add_trace_id(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor that stamps the active ``trace_id`` onto every event."""
    trace_id = trace_id_var.get()
    if trace_id is not None:
        event_dict.setdefault("trace_id", trace_id)
    return event_dict


def configure_logging(*, level: str | None = None, json_logs: bool | None = None) -> None:
    """Configure structlog process-wide. Idempotent.

    Args:
        level: Log level name (e.g. ``"INFO"``). Defaults to ``settings.log_level``.
        json_logs: Emit JSON (production) when ``True``, pretty console output
            when ``False``. Defaults to ``settings.log_json``.
    """
    global _configured

    resolved_level = (level or settings.log_level).upper()
    resolved_json = settings.log_json if json_logs is None else json_logs
    level_number = logging.getLevelName(resolved_level)
    if not isinstance(level_number, int):
        level_number = logging.INFO

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_trace_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if resolved_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level_number),
        # Logs go to stderr so stdout stays clean for data (script output) and,
        # critically, for the MCP stdio JSON-RPC protocol.
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, configuring logging on first use."""
    if not _configured:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def new_trace_id() -> str:
    """Generate a fresh hex trace id."""
    return uuid4().hex


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """Bind a ``trace_id`` for the duration of the ``with`` block.

    Args:
        trace_id: An existing trace id to adopt (e.g. propagated from an
            incoming request). A new one is generated when omitted.

    Yields:
        The active trace id.
    """
    resolved = trace_id or new_trace_id()
    token = trace_id_var.set(resolved)
    try:
        yield resolved
    finally:
        trace_id_var.reset(token)


__all__ = [
    "configure_logging",
    "get_logger",
    "new_trace_id",
    "trace_context",
    "trace_id_var",
]
