"""FastAPI application entry point.

Milestone 1 ships health endpoints only, but ``app`` here is the **canonical**
application object: later milestones attach their ``/api/v1/*`` routes and the
SSE streaming endpoints to this same instance (not a parallel app).

Endpoints:

* ``GET /health``       — liveness; always 200 if the process is up.
* ``GET /health/ready`` — readiness; pings ChromaDB with a short timeout and
  returns 503 if the dependency is unavailable/slow, so orchestrators don't
  route traffic to a degraded instance.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from clauseiq import __version__
from clauseiq.config import settings
from clauseiq.domain.ports import VectorStore
from clauseiq.infrastructure.vectorstore.chroma import build_law_vector_store
from clauseiq.logging_config import configure_logging, get_logger

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


def create_app() -> FastAPI:
    """Construct the canonical FastAPI application."""
    app = FastAPI(
        title="ClauseIQ API",
        version=__version__,
        summary="Multi-agent analysis of Indian contracts with cited law.",
        lifespan=lifespan,
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
                status_code=503,
                content={"status": "degraded", "dependency": "chromadb"},
            )
        return JSONResponse({"status": "ready", "indexed_chunks": indexed})

    return app


app = create_app()


__all__ = ["app", "create_app"]
