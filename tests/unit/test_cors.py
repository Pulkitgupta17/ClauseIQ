"""Tests for the CORS middleware that lets the browser frontend call the API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import clauseiq.interfaces.api.main as api_main


def _app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Stub the vector store so no ChromaDB is needed; preflight never hits a route.
    monkeypatch.setattr(api_main, "build_law_vector_store", lambda: object())
    return TestClient(api_main.create_app())


def test_cors_preflight_allows_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app(monkeypatch)
    response = client.options(
        "/api/v1/analyze",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_does_not_allow_unknown_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app(monkeypatch)
    response = client.options(
        "/api/v1/analyze",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Whether Starlette returns 200 or 400, the allow-origin header must be absent.
    assert response.headers.get("access-control-allow-origin") is None
