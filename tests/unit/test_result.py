"""Unit tests for the ``Result[T, E]`` type."""

from __future__ import annotations

import pytest

from clauseiq.domain.exceptions import RetrievalError, UnwrapError
from clauseiq.domain.result import Err, Ok, Result, is_err, is_ok


def test_ok_basic_accessors() -> None:
    result: Result[int, str] = Ok(42)
    assert result.is_ok() is True
    assert result.is_err() is False
    assert result.ok() == 42
    assert result.err() is None
    assert is_ok(result) is True
    assert is_err(result) is False


def test_err_basic_accessors() -> None:
    result: Result[int, str] = Err("boom")
    assert result.is_ok() is False
    assert result.is_err() is True
    assert result.ok() is None
    assert result.err() == "boom"
    assert is_ok(result) is False
    assert is_err(result) is True


def test_ok_unwrap_returns_value() -> None:
    assert Ok(7).unwrap() == 7
    assert Ok(7).expect("should have a value") == 7
    assert Ok(7).unwrap_or(0) == 7
    assert Ok(7).unwrap_or_else(lambda _: 0) == 7


def test_ok_unwrap_err_raises() -> None:
    with pytest.raises(UnwrapError):
        Ok(7).unwrap_err()


def test_err_unwrap_raises_and_chains_cause() -> None:
    original = RetrievalError("no_results")
    err: Result[int, RetrievalError] = Err(original)
    with pytest.raises(UnwrapError) as exc_info:
        err.unwrap()
    assert exc_info.value.__cause__ is original


def test_err_unwrap_or_returns_default() -> None:
    err: Result[int, str] = Err("bad")
    assert err.unwrap_or(99) == 99
    assert err.unwrap_or_else(len) == 3
    assert err.unwrap_err() == "bad"


def test_err_expect_raises_with_message() -> None:
    with pytest.raises(UnwrapError, match="custom message"):
        Err("bad").expect("custom message")


def test_map_transforms_only_ok() -> None:
    assert Ok(2).map(lambda x: x * 10) == Ok(20)
    err: Result[int, str] = Err("e")
    assert err.map(lambda x: x * 10) == Err("e")


def test_map_err_transforms_only_err() -> None:
    assert Err("e").map_err(str.upper) == Err("E")
    ok: Result[int, str] = Ok(5)
    assert ok.map_err(str.upper) == Ok(5)


def test_and_then_chains_and_short_circuits() -> None:
    def half(x: int) -> Result[float, str]:
        return Ok(x / 2) if x % 2 == 0 else Err("odd")

    assert Ok(8).and_then(half) == Ok(4.0)
    assert Ok(7).and_then(half) == Err("odd")
    err: Result[int, str] = Err("upstream")
    assert err.and_then(half) == Err("upstream")


def test_pattern_matching() -> None:
    def describe(result: Result[int, str]) -> str:
        match result:
            case Ok(value):
                return f"ok:{value}"
            case Err(error):
                return f"err:{error}"

    assert describe(Ok(1)) == "ok:1"
    assert describe(Err("x")) == "err:x"


def test_results_are_immutable() -> None:
    ok = Ok(1)
    with pytest.raises((AttributeError, TypeError)):
        ok.value = 2  # type: ignore[misc]
