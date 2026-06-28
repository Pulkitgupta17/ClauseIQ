"""Tests for the @traced decorator and Langfuse span emission (fake client)."""

from __future__ import annotations

from typing import Any

import pytest

import clauseiq.infrastructure.observability.langfuse_client as lf
from clauseiq.infrastructure.observability.langfuse_client import traced
from clauseiq.infrastructure.observability.usage import record_usage, usage_scope


class _FakeTrace:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, Any]]] = []

    def span(self, *, name: str, metadata: dict[str, Any]) -> None:
        self.spans.append((name, metadata))


class _FakeLangfuse:
    def __init__(self) -> None:
        self.traces: dict[str, _FakeTrace] = {}

    def trace(self, *, id: str, name: str) -> _FakeTrace:
        return self.traces.setdefault(id, _FakeTrace())


async def test_traced_returns_value_and_records_span(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeLangfuse()
    monkeypatch.setattr(lf, "get_langfuse", lambda: fake)

    @traced("unit_node")
    async def work(value: int) -> int:
        record_usage("gemini-2.0-flash", 1000, 500)
        return value * 2

    with usage_scope():
        result = await work(21)

    assert result == 42
    (trace,) = fake.traces.values()
    name, metadata = trace.spans[0]
    assert name == "unit_node"
    assert metadata["agent_name"] == "unit_node"
    assert metadata["tokens_used"] == 1500
    assert metadata["prompt_tokens"] == 1000
    assert metadata["cost_usd"] > 0
    assert metadata["latency_ms"] >= 0


async def test_traced_attributes_only_its_own_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeLangfuse()
    monkeypatch.setattr(lf, "get_langfuse", lambda: fake)

    @traced("inner")
    async def inner() -> None:
        record_usage("gemini-2.5-pro", 200, 100)

    with usage_scope():
        record_usage("gemini-2.0-flash", 50, 50)  # usage before the traced call
        await inner()

    metadata = next(iter(fake.traces.values())).spans[0][1]
    # Only the 300 tokens recorded inside `inner` are attributed to it.
    assert metadata["tokens_used"] == 300


async def test_traced_is_noop_without_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lf, "get_langfuse", lambda: None)

    @traced("unit")
    async def work() -> str:
        return "ok"

    assert await work() == "ok"


async def test_traced_swallows_langfuse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Exploding:
        def trace(self, *, id: str, name: str) -> Any:
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(lf, "get_langfuse", lambda: _Exploding())

    @traced("unit")
    async def work() -> str:
        return "ok"

    # Tracing failure must not break the wrapped call.
    assert await work() == "ok"
