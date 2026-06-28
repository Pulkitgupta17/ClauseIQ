"""Application configuration via 12-factor environment variables.

All settings are read from the environment (optionally seeded by a local
``.env`` file) with the ``CLAUSEIQ_`` prefix, e.g. ``CLAUSEIQ_CHROMA_PORT=8001``.

Design notes
------------
* **Secrets are optional with empty defaults.** Per 12-factor, config must load
  even when a particular capability's credentials are absent — the data
  pipeline (ingestion + retrieval) runs with no LLM/Langfuse keys at all. The
  LLM/observability factories validate presence *at point of use* and surface a
  typed failure, rather than crashing the whole process at import time.
* **One module-level :data:`settings` instance** is created eagerly so importers
  share a single, validated configuration object.
* **``corpus_version``** is derived from the law-corpus JSON's top-level
  ``version`` field when not set explicitly, so the value flows into
  :class:`~clauseiq.domain.entities.Citation` objects for freshness tracking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_UNVERSIONED = "unversioned"


def _read_corpus_version(path: Path) -> str:
    """Read the ``version`` field from the law-corpus JSON.

    Returns ``"unversioned"`` if the file is missing, unreadable, malformed, or
    has no top-level ``version`` — never raises, because configuration loading
    must not depend on a data file that is generated later in the pipeline.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            data: object = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _UNVERSIONED
    if isinstance(data, dict):
        version = data.get("version")
        if version:
            return str(version)
    return _UNVERSIONED


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLAUSEIQ_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLMs (Google AI Studio, free tier) ---------------------------------
    # SecretStr so the key never appears in logs, reprs, or tracebacks; read it
    # explicitly with `.get_secret_value()` only where the SDK needs it.
    gemini_api_key: SecretStr = SecretStr("")
    orchestration_model: str = "gemini-2.0-flash"
    analysis_model: str = "gemini-2.5-pro"

    # --- Embeddings (local, free) -------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Vector store --------------------------------------------------------
    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8000, ge=1, le=65535)
    chroma_collection_law: str = "indian_law"
    chroma_persist_dir: Path = Path("data/chroma")
    # "embedded" = local PersistentClient (default; no server needed for dev/CI/tests);
    # "http" = connect to a ChromaDB server at chroma_host:chroma_port (Docker compose).
    chroma_mode: Literal["embedded", "http"] = "embedded"

    # --- Chunking (defaults aligned to all-MiniLM-L6-v2's 256-token window) --
    chunk_max_tokens: int = Field(default=250, ge=1)
    chunk_overlap_tokens: int = Field(default=25, ge=0)

    # --- Law corpus (committed JSON = source of truth) ----------------------
    law_corpus_path: Path = Path("data/laws/indian_contract_act_1872.json")
    corpus_version: str = ""

    # --- Observability (Langfuse, self-hosted) ------------------------------
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # --- Eval thresholds -----------------------------------------------------
    faithfulness_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    context_recall_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    # --- Web / CORS ----------------------------------------------------------
    # Origins allowed to call the API from a browser. Defaults cover the Vite dev
    # server (5173) and preview (4173); set CLAUSEIQ_CORS_ALLOWED_ORIGINS (JSON
    # list) for deployed frontends. Never use "*" with credentials.
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"],
    )

    # --- Runtime / logging ---------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    environment: Literal["dev", "test", "prod"] = "dev"

    @model_validator(mode="after")
    def _validate_chunking(self) -> Settings:
        """Ensure the chunk overlap is strictly smaller than the chunk size."""
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            msg = (
                "chunk_overlap_tokens must be < chunk_max_tokens "
                f"(got overlap={self.chunk_overlap_tokens}, max={self.chunk_max_tokens})"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _resolve_corpus_version(self) -> Settings:
        """Derive ``corpus_version`` from the corpus file when not set in env."""
        if not self.corpus_version:
            self.corpus_version = _read_corpus_version(self.law_corpus_path)
        return self


settings = Settings()
"""The process-wide, validated settings instance."""


__all__ = ["Settings", "settings"]
