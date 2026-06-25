"""Unit tests for the domain exception hierarchy."""

from __future__ import annotations

import pytest

from clauseiq.domain.exceptions import (
    ClauseIQError,
    IngestionError,
    LowConfidenceError,
    PDFParsingError,
    RetrievalError,
)


def test_default_code_is_class_name() -> None:
    err = RetrievalError("no_results")
    assert err.code == "RetrievalError"
    assert err.message == "no_results"
    assert err.context == {}


def test_explicit_code_and_context() -> None:
    err = RetrievalError("infra_failure", code="RETRIEVAL_INFRA", query="void contract", k=5)
    assert err.code == "RETRIEVAL_INFRA"
    assert err.context == {"query": "void contract", "k": 5}


def test_cause_is_wired_to_dunder_cause() -> None:
    root = ValueError("connection refused")
    err = RetrievalError("infra_failure", cause=root)
    assert err.cause is root
    assert err.__cause__ is root


def test_str_without_context() -> None:
    assert str(RetrievalError("no_results")) == "no_results"


def test_str_with_context_renders_pairs() -> None:
    rendered = str(RetrievalError("no_results", query="abc", k=3))
    assert rendered.startswith("no_results (")
    assert "query='abc'" in rendered
    assert "k=3" in rendered


def test_repr_includes_code_and_context() -> None:
    text = repr(RetrievalError("boom", k=1))
    assert "RetrievalError" in text
    assert "code=" in text
    assert "context=" in text


def test_hierarchy_is_catchable_as_base() -> None:
    assert issubclass(PDFParsingError, IngestionError)
    assert issubclass(IngestionError, ClauseIQError)
    assert issubclass(LowConfidenceError, ClauseIQError)
    with pytest.raises(ClauseIQError):
        raise PDFParsingError("cannot open pdf")
