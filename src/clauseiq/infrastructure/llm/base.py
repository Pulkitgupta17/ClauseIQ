"""LLM client port and the shared Gemini implementation.

``LLMClient`` is the port the application depends on. ``GeminiClient`` implements
it over ``google-genai``:

* ``generate`` returns free text.
* ``generate_structured`` forces JSON matching a Pydantic schema (via the SDK's
  ``response_schema``) and returns the validated model — this is how agents get
  reliable, typed output instead of parsing prose.

Every call is wrapped in a ``Result``: expected failures (missing key, rate
limit after retries, malformed structured output) are ``Err(LLMError)``, never
exceptions. Transient errors (HTTP 429/5xx) are retried with exponential backoff.

``Any`` appears where it touches the ``google-genai`` SDK, which ships no useful
types for the client/response/config objects; values are narrowed before use.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from clauseiq.config import settings
from clauseiq.domain.exceptions import ConfigurationError, LLMError
from clauseiq.domain.result import Err, Ok, Result
from clauseiq.logging_config import get_logger

log = get_logger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

# HTTP status codes worth retrying (rate limit + transient server errors).
_TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})


@runtime_checkable
class LLMClient(Protocol):
    """Port for an LLM that can produce text or schema-validated structured output."""

    model_name: str

    async def generate(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Result[str, LLMError]:
        """Generate free-text completion for ``prompt``."""
        ...

    async def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Result[TModel, LLMError]:
        """Generate JSON conforming to ``schema`` and return the validated model."""
        ...


class GeminiClient:
    """Async Gemini client implementing :class:`LLMClient`.

    Args:
        model_name: Gemini model id (e.g. ``"gemini-2.0-flash"``).
        api_key: Overrides ``settings.gemini_api_key`` when provided.
        client: An injected SDK client (for testing); built lazily otherwise.
        max_retries: Attempts before giving up on transient failures.
        base_delay: Initial backoff delay in seconds (doubles each retry).
    """

    def __init__(
        self,
        model_name: str,
        *,
        api_key: str | None = None,
        client: Any = None,  # google-genai Client; untyped SDK
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> None:
        self.model_name = model_name
        self._api_key = api_key
        self._client: Any = client
        self._max_retries = max_retries
        self._base_delay = base_delay

    def _ensure_client(self) -> Any:  # returns google-genai Client (untyped SDK)
        if self._client is None:
            key = self._api_key or settings.gemini_api_key
            if not key:
                raise ConfigurationError("gemini_api_key_missing", model=self.model_name)
            from google import genai

            self._client = genai.Client(api_key=key)
        return self._client

    def _build_config(
        self, system: str | None, temperature: float | None, schema: type[BaseModel] | None
    ) -> Any:  # google-genai GenerateContentConfig (untyped SDK)
        from google.genai import types as genai_types

        config: dict[str, Any] = {}
        if system:
            config["system_instruction"] = system
        if temperature is not None:
            config["temperature"] = temperature
        if schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = schema
        return genai_types.GenerateContentConfig(**config)

    @staticmethod
    def _is_transient(code: object) -> bool:
        return isinstance(code, int) and code in _TRANSIENT_CODES

    async def _call(self, prompt: str, config: Any) -> Result[Any, LLMError]:
        """Run a generation with retry; return the raw SDK response or an error."""
        try:
            client = self._ensure_client()
        except ConfigurationError as exc:
            return Err(LLMError("api_key_missing", cause=exc, model=self.model_name))

        delay = self._base_delay
        for attempt in range(self._max_retries):
            try:
                response = await client.aio.models.generate_content(
                    model=self.model_name, contents=prompt, config=config
                )
            except Exception as exc:  # google-genai boundary
                code = getattr(exc, "code", None)
                if self._is_transient(code) and attempt < self._max_retries - 1:
                    log.warning("llm_retry", model=self.model_name, attempt=attempt, code=code)
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                log.error("llm_call_failed", model=self.model_name, code=code, error=str(exc))
                return Err(
                    LLMError(
                        "generation_failed", cause=exc, model=self.model_name, status_code=code
                    )
                )
            else:
                return Ok(response)
        return Err(LLMError("retries_exhausted", model=self.model_name))

    async def generate(
        self, prompt: str, *, system: str | None = None, temperature: float | None = None
    ) -> Result[str, LLMError]:
        config = self._build_config(system, temperature, None)
        result = await self._call(prompt, config)
        if result.is_err():
            return Err(result.unwrap_err())
        text = getattr(result.unwrap(), "text", None)
        if not isinstance(text, str) or not text.strip():
            return Err(LLMError("empty_response", model=self.model_name))
        return Ok(text)

    async def generate_structured(
        self,
        prompt: str,
        schema: type[TModel],
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Result[TModel, LLMError]:
        config = self._build_config(system, temperature, schema)
        result = await self._call(prompt, config)
        if result.is_err():
            return Err(result.unwrap_err())
        parsed = getattr(result.unwrap(), "parsed", None)
        try:
            model = parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
        except (ValueError, TypeError) as exc:  # pydantic ValidationError is a ValueError
            return Err(LLMError("structured_parse_failed", cause=exc, model=self.model_name))
        return Ok(model)


__all__ = ["GeminiClient", "LLMClient", "TModel"]
