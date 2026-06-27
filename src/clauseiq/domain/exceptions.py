"""Domain exception hierarchy for ClauseIQ.

Two distinct failure-handling mechanisms coexist in this codebase, and it is
important not to confuse them:

* **Expected, recoverable failures** (no results, low confidence, an upstream
  service being briefly unavailable) are modelled with the :class:`Result`
  type — see :mod:`clauseiq.domain.result`. These are part of a function's
  normal contract and callers must handle them.
* **Exceptions** (this module) represent either invariant violations / bugs in
  the pure domain, *or* the structured error payload that is carried **inside**
  an ``Err`` value across a boundary — e.g. ``Result[list[Chunk],
  RetrievalError]``.

Every exception derives from :class:`ClauseIQError`, so callers can catch the
entire family with a single explicit ``except ClauseIQError`` and never need a
bare ``except``.
"""

from __future__ import annotations


class ClauseIQError(Exception):
    """Base class for every ClauseIQ domain and application error.

    Args:
        message: Human-readable text, or a short machine code such as
            ``"no_results"``. Stored verbatim on :attr:`message`.
        code: Stable machine-readable identifier used in logs and API error
            envelopes. Defaults to the concrete class name, so every error has a
            predictable ``code`` even when one is not supplied explicitly.
        cause: The originating lower-level exception, when this error wraps one.
            It is also assigned to ``__cause__`` so tracebacks chain naturally
            (equivalent to ``raise ... from cause``).
        **context: Arbitrary structured key/value pairs surfaced in structured
            logs and useful for debugging. Values are typed as ``object`` (not
            ``Any``) because they are only ever rendered, never operated on.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        cause: Exception | None = None,
        **context: object,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.cause = cause
        self.context: dict[str, object] = dict(context)
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(f"{key}={value!r}" for key, value in self.context.items())
        return f"{self.message} ({rendered})"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.message!r}, "
            f"code={self.code!r}, context={self.context!r})"
        )


# --- Configuration & input validation ---------------------------------------


class ConfigurationError(ClauseIQError):
    """Invalid or missing configuration (env vars, settings)."""


class ValidationError(ClauseIQError):
    """A domain invariant was violated by caller-supplied input."""


# --- Ingestion ---------------------------------------------------------------


class IngestionError(ClauseIQError):
    """Base for the ingestion pipeline (parsing, chunking, loading)."""


class PDFParsingError(IngestionError):
    """A PDF could not be opened or text could not be extracted."""


class ChunkingError(IngestionError):
    """Text could not be chunked (e.g. invalid chunk parameters)."""


# --- Vector store & retrieval ------------------------------------------------


class VectorStoreError(ClauseIQError):
    """The vector store backend failed (connection, write, query)."""


class EmbeddingError(ClauseIQError):
    """The embedding model failed to produce vectors."""


class LLMError(ClauseIQError):
    """An LLM call failed: generation, structured parsing, missing key, or rate limit."""


class RetrievalError(ClauseIQError):
    """Retrieval failed or returned nothing usable."""


class LowConfidenceError(ClauseIQError):
    """Retrieval returned results below the configured confidence threshold."""


class AnalysisError(ClauseIQError):
    """The contract-analysis pipeline failed to produce a result."""


class GuardrailError(ClauseIQError):
    """Input rejected by a guardrail (not a contract, or a prompt-injection attempt)."""


# --- Repositories ------------------------------------------------------------


class RepositoryError(ClauseIQError):
    """A repository operation failed."""


class LawSectionNotFoundError(RepositoryError):
    """A requested statutory section does not exist in the corpus."""


# --- Result misuse -----------------------------------------------------------


class UnwrapError(ClauseIQError):
    """Raised when ``unwrap``/``unwrap_err`` is called on the wrong variant."""


__all__ = [
    "AnalysisError",
    "ChunkingError",
    "ClauseIQError",
    "ConfigurationError",
    "EmbeddingError",
    "GuardrailError",
    "IngestionError",
    "LLMError",
    "LawSectionNotFoundError",
    "LowConfidenceError",
    "PDFParsingError",
    "RepositoryError",
    "RetrievalError",
    "UnwrapError",
    "ValidationError",
    "VectorStoreError",
]
