# Three stages: a builder that installs deps with uv, an indexer that bakes the
# ChromaDB vector index + embedding-model cache at build time, and a slim runtime.
# (No BuildKit cache-mounts — Cloud Build's classic docker builder doesn't support them.)

FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Install runtime dependencies first (cached layer keyed on the lockfile).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself (editable, src layout).
COPY src ./src
RUN uv sync --frozen --no-dev


# Bake the vector index and cache the embedding model (bake-at-build: no runtime
# ingestion, no persistent disk needed). Ingestion is fully local — no API key.
FROM builder AS indexer

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_XET=1
COPY data/laws ./data/laws
COPY scripts/ingest_laws.py ./scripts/ingest_laws.py
RUN python scripts/ingest_laws.py


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_OFFLINE=1
WORKDIR /app

# Non-root runtime user.
RUN useradd --create-home --uid 1000 app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY data/laws ./data/laws
# Pre-built index + model cache from the indexer stage.
COPY --from=indexer /app/data/chroma ./data/chroma
COPY --from=indexer /app/.cache/huggingface ./.cache/huggingface

RUN chown -R app:app /app
USER app

EXPOSE 8000

# Render (and most PaaS) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn clauseiq.interfaces.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
