"""Tests for the health endpoints (liveness + readiness)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import clauseiq.interfaces.api.main as api_main
from clauseiq.domain.exceptions import VectorStoreError


class _ReadyStore:
    async def count(self) -> int:
        return 42


class _DegradedStore:
    async def count(self) -> int:
        raise VectorStoreError("chromadb_unreachable")


def _client(monkeypatch: pytest.MonkeyPatch, store: object) -> TestClient:
    monkeypatch.setattr(api_main, "build_law_vector_store", lambda: store)
    return TestClient(api_main.create_app())


def test_health_is_always_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, _ReadyStore()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_ok_when_chromadb_responds(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, _ReadyStore()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "indexed_chunks": 42}


def test_readiness_503_when_chromadb_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch, _DegradedStore()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
