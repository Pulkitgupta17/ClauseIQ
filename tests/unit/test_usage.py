"""Unit tests for token usage accounting and cost computation."""

from __future__ import annotations

import pytest

from clauseiq.infrastructure.observability.usage import (
    UsageTotals,
    cost_for,
    current_usage,
    record_usage,
    usage_scope,
)


def test_cost_for_known_models() -> None:
    # 1M input tokens on Flash = $0.10; 1M output on Pro = $10.
    assert cost_for("gemini-2.0-flash", 1_000_000, 0) == pytest.approx(0.10)
    assert cost_for("gemini-2.5-pro", 0, 1_000_000) == pytest.approx(10.0)


def test_cost_for_unknown_model_uses_default() -> None:
    assert cost_for("some-unknown-model", 1_000_000, 0) == pytest.approx(0.10)


def test_usage_totals_record_snapshot_and_delta() -> None:
    totals = UsageTotals()
    totals.record("gemini-2.0-flash", 100, 50)
    assert totals.total_tokens == 150
    snapshot = totals.snapshot()
    totals.record("gemini-2.5-pro", 200, 100)
    delta = totals.since(snapshot)
    assert (delta.prompt_tokens, delta.completion_tokens, delta.total_tokens) == (200, 100, 300)
    assert delta.cost_usd > 0


def test_usage_scope_accumulates_and_resets() -> None:
    assert current_usage() is None
    with usage_scope() as totals:
        record_usage("gemini-2.0-flash", 1000, 500)
        record_usage("gemini-2.5-pro", 2000, 1000)
        assert totals.total_tokens == 4500
        assert current_usage() is totals
        assert totals.cost_usd > 0
    assert current_usage() is None


def test_record_usage_is_noop_without_scope() -> None:
    record_usage("gemini-2.0-flash", 100, 100)  # must not raise
    assert current_usage() is None


def test_nested_usage_scopes_accumulate_into_parent() -> None:
    # An outer scope (e.g. an eval runner) must see usage recorded inside an inner
    # scope (e.g. analyze() opening its own scope).
    with usage_scope() as outer:
        with usage_scope() as inner:
            record_usage("gemini-2.5-pro", 1000, 500)
            assert inner.total_tokens == 1500
        assert current_usage() is outer
        assert outer.total_tokens == 1500
        assert outer.cost_usd > 0
