"""Unit tests for the LLM layer (google-genai SDK is faked; no API key, no network)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from clauseiq.domain.result import Ok
from clauseiq.infrastructure.llm.base import GeminiClient, LLMClient
from clauseiq.infrastructure.llm.factory import LLMRole, get_llm_client


class _Demo(BaseModel):
    label: str
    score: int


class _ApiError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"http {code}")
        self.code = code


class _FakeResponse:
    def __init__(self, *, text: str | None = None, parsed: object = None) -> None:
        self.text = text
        self.parsed = parsed


class _FakeModels:
    def __init__(
        self, *, response: _FakeResponse | None = None, errors: list[Exception] | None = None
    ) -> None:
        self._response = response
        self._errors = list(errors or [])
        self.calls = 0

    async def generate_content(self, *, model: str, contents: str, config: Any) -> _FakeResponse:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        assert self._response is not None
        return self._response


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = type("_Aio", (), {"models": models})()


def _client(models: _FakeModels) -> GeminiClient:
    return GeminiClient("gemini-test", client=_FakeClient(models), base_delay=0.0)


# --- text generation ---------------------------------------------------------


async def test_generate_returns_text() -> None:
    client = _client(_FakeModels(response=_FakeResponse(text="hello world")))
    result = await client.generate("hi", system="be terse")
    assert result == Ok("hello world")


async def test_generate_empty_response_is_error() -> None:
    result = await _client(_FakeModels(response=_FakeResponse(text="  "))).generate("hi")
    assert result.is_err()
    assert result.unwrap_err().message == "empty_response"


# --- structured generation ---------------------------------------------------


async def test_generate_structured_returns_model_instance() -> None:
    models = _FakeModels(response=_FakeResponse(parsed=_Demo(label="risk", score=4)))
    result = await _client(models).generate_structured("analyze", _Demo)
    assert result.is_ok()
    assert result.unwrap().score == 4


async def test_generate_structured_validates_dict_payload() -> None:
    models = _FakeModels(response=_FakeResponse(parsed={"label": "risk", "score": 2}))
    result = await _client(models).generate_structured("analyze", _Demo)
    assert result.is_ok()
    assert result.unwrap() == _Demo(label="risk", score=2)


async def test_generate_structured_parse_failure_is_error() -> None:
    models = _FakeModels(response=_FakeResponse(parsed={"label": "x"}))  # missing 'score'
    result = await _client(models).generate_structured("analyze", _Demo)
    assert result.is_err()
    assert result.unwrap_err().message == "structured_parse_failed"


# --- retry / error handling --------------------------------------------------


async def test_retries_transient_then_succeeds() -> None:
    models = _FakeModels(response=_FakeResponse(text="ok"), errors=[_ApiError(503)])
    result = await _client(models).generate("hi")
    assert result.is_ok()
    assert models.calls == 2  # one failure + one success


async def test_does_not_retry_non_transient() -> None:
    models = _FakeModels(errors=[_ApiError(400)])
    result = await _client(models).generate("hi")
    assert result.is_err()
    assert models.calls == 1
    assert result.unwrap_err().context.get("status_code") == 400


async def test_missing_api_key_is_error() -> None:
    # No injected client and no configured key -> typed failure, not a crash.
    result = await GeminiClient("gemini-test").generate("hi")
    assert result.is_err()
    assert result.unwrap_err().message == "api_key_missing"


# --- factory -----------------------------------------------------------------


def test_factory_returns_role_specific_clients() -> None:
    fake = _FakeClient(_FakeModels(response=_FakeResponse(text="x")))
    orchestration = get_llm_client(LLMRole.ORCHESTRATION, client=fake)
    analysis = get_llm_client(LLMRole.ANALYSIS, client=fake)
    assert isinstance(orchestration, LLMClient)
    assert isinstance(analysis, LLMClient)
    assert "flash" in orchestration.model_name
    assert "pro" in analysis.model_name


@pytest.mark.parametrize("role", list(LLMRole))
def test_factory_clients_satisfy_protocol(role: LLMRole) -> None:
    assert isinstance(get_llm_client(role), LLMClient)
