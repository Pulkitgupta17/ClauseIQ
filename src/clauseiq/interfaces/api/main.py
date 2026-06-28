"""FastAPI application entry point — the canonical ``app``.

Wires middleware, exception handlers, health endpoints, and the ``/api/v1``
routes (analysis + SSE + law drill-down) onto a single FastAPI instance.

* Middleware stamps each request with a ``trace_id`` (propagated to logs and the
  ``X-Trace-Id`` response header) and logs latency.
* Exception handlers turn domain errors into clean JSON envelopes and ensure an
  unexpected error never leaks internals (only a ``trace_id`` for correlation).

Endpoints: ``GET /health`` (liveness), ``GET /health/ready`` (readiness, pings
ChromaDB), plus the routes in :mod:`clauseiq.interfaces.api.routes`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from clauseiq import __version__
from clauseiq.config import settings
from clauseiq.domain.exceptions import ClauseIQError, LawSectionNotFoundError, ValidationError
from clauseiq.domain.ports import VectorStore
from clauseiq.infrastructure.vectorstore.chroma import build_law_vector_store
from clauseiq.interfaces.api.routes import router
from clauseiq.logging_config import configure_logging, get_logger, trace_context, trace_id_var

log = get_logger(__name__)

# Readiness must fail fast; never let a slow dependency hang the probe.
READINESS_TIMEOUT_SECONDS = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared, long-lived resources once per process."""
    configure_logging()
    app.state.law_store = build_law_vector_store()
    log.info("api_startup", environment=settings.environment, version=__version__)
    yield
    log.info("api_shutdown")


def _status_for(error: ClauseIQError) -> int:
    if isinstance(error, ValidationError):
        return 422
    if isinstance(error, LawSectionNotFoundError):
        return 404
    return 500


def create_app() -> FastAPI:
    """Construct the canonical FastAPI application."""
    app = FastAPI(
        title="ClauseIQ API",
        version=__version__,
        summary="Multi-agent analysis of Indian contracts with cited law.",
        lifespan=lifespan,
    )

    # CORS for browser clients (the React app). Added last so it runs outermost,
    # ensuring preflight OPTIONS requests get the headers before anything else.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def trace_and_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Bind a trace id for the request and log method/path/status/latency."""
        incoming = request.headers.get("X-Trace-Id")
        with trace_context(incoming) as trace_id:
            started = time.perf_counter()
            log.info("request_start", method=request.method, path=request.url.path)
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            log.info(
                "request_end",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response

    @app.exception_handler(ClauseIQError)
    async def handle_domain_error(_request: Request, exc: ClauseIQError) -> JSONResponse:
        status = _status_for(exc)
        log.warning("domain_error", code=exc.code, message=exc.message, status=status)
        return JSONResponse(
            status_code=status,
            content={"error": exc.code, "message": exc.message, "trace_id": trace_id_var.get()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals; surface only a correlation id.
        log.error("unhandled_error", error=str(exc), error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "trace_id": trace_id_var.get()},
        )

    @app.get("/health", tags=["health"])
    async def health() -> JSONResponse:
        """Liveness probe — 200 whenever the process is running."""
        return JSONResponse({"status": "ok", "version": __version__})

    @app.get("/health/ready", tags=["health"])
    async def readiness() -> JSONResponse:
        """Readiness probe — 200 only when ChromaDB answers within the timeout."""
        store: VectorStore = app.state.law_store
        try:
            indexed = await asyncio.wait_for(store.count(), timeout=READINESS_TIMEOUT_SECONDS)
        except Exception as exc:  # any failure => degraded; readiness must not raise
            log.warning("readiness_degraded", dependency="chromadb", error=str(exc))
            return JSONResponse(
                status_code=503, content={"status": "degraded", "dependency": "chromadb"}
            )
        return JSONResponse({"status": "ready", "indexed_chunks": indexed})

    app.include_router(router)
    return app


app = create_app()


__all__ = ["app", "create_app"]
