# syntax=docker/dockerfile:1
# Multi-stage build: a heavy builder that resolves/installs dependencies with uv,
# and a slim runtime that only carries the virtualenv + source.

FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Install runtime dependencies first (cached layer keyed on the lockfile).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Install the project itself (editable, src layout).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface
WORKDIR /app

# Non-root runtime user.
RUN useradd --create-home --uid 1000 app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY data/laws ./data/laws

RUN mkdir -p /app/data/chroma /app/.cache && chown -R app:app /app
USER app

EXPOSE 8000

# The canonical FastAPI app (health endpoints in M1; full API in later milestones).
CMD ["uvicorn", "clauseiq.interfaces.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
