"""Langfuse client and the ``@traced`` decorator.

``@traced(name)`` wraps an async agent node or tool call and, on completion,
records ``trace_id``, ``agent_name``, ``latency_ms``, ``tokens_used`` and
``cost_usd``:

* **always** to structlog (so cost is logged and visible per request even with
  no Langfuse), and
* to **Langfuse** when keys are configured — as a span under one trace per
  analysis (keyed by ``trace_id``), best-effort and fully guarded so tracing
  never breaks an analysis.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from clauseiq.config import settings
from clauseiq.infrastructure.observability.usage import UsageTotals, current_usage
from clauseiq.logging_config import ensure_trace, get_logger

log = get_logger(__name__)

_AsyncFn = TypeVar("_AsyncFn", bound=Callable[..., Awaitable[Any]])

_langfuse: Any = None  # langfuse.Langfuse | None; SDK is untyped here
_initialised = False


def get_langfuse() -> Any:
    """Return a cached Langfuse client, or ``None`` when not configured."""
    global _langfuse, _initialised
    if _initialised:
        return _langfuse
    _initialised = True
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            from langfuse import Langfuse

            _langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            log.info("langfuse_enabled", host=settings.langfuse_host)
        except Exception as exc:  # never let observability setup break the app
            log.warning("langfuse_init_failed", error=str(exc))
            _langfuse = None
    return _langfuse


def reset_langfuse_cache() -> None:
    """Reset the cached client (used by tests)."""
    global _langfuse, _initialised
    _langfuse = None
    _initialised = False


def _emit_span(name: str, trace_id: str | None, latency_ms: float, usage: UsageTotals) -> None:
    """Best-effort: record a span under the analysis trace in Langfuse."""
    client = get_langfuse()
    if client is None:
        return
    try:
        trace = client.trace(id=trace_id or "untraced", name="contract_analysis")
        trace.span(
            name=name,
            metadata={
                "agent_name": name,
                "latency_ms": latency_ms,
                "tokens_used": usage.total_tokens,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost_usd": round(usage.cost_usd, 6),
            },
        )
    except Exception as exc:  # tracing must never break the analysis
        log.warning("langfuse_span_failed", agent_name=name, error=str(exc))


def traced(name: str) -> Callable[[_AsyncFn], _AsyncFn]:
    """Decorate an async agent node / tool to record its trace fields on completion."""

    def decorator(fn: _AsyncFn) -> _AsyncFn:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            before = current_usage()
            before_snapshot = before.snapshot() if before is not None else None
            started = time.perf_counter()
            with ensure_trace() as trace_id:
                try:
                    return await fn(*args, **kwargs)
                finally:
                    latency_ms = round((time.perf_counter() - started) * 1000, 2)
                    after = current_usage()
                    delta = (
                        after.since(before_snapshot)
                        if after is not None and before_snapshot is not None
                        else UsageTotals()
                    )
                    log.info(
                        "traced",
                        agent_name=name,
                        trace_id=trace_id,
                        latency_ms=latency_ms,
                        tokens_used=delta.total_tokens,
                        cost_usd=round(delta.cost_usd, 6),
                    )
                    _emit_span(name, trace_id, latency_ms, delta)

        return cast(_AsyncFn, wrapper)

    return decorator


__all__ = ["get_langfuse", "reset_langfuse_cache", "traced"]
