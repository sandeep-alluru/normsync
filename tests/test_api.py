"""Tests for FastAPI REST API."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Reset module-level store and monitor for test isolation
    import importlib

    import normsync.api as api_module

    importlib.reload(api_module)
    from normsync.api import app

    return TestClient(app)


class TestApiHealth:
    def test_health_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_status_ok(self, client):
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_health_has_version(self, client):
        r = client.get("/health")
        assert "version" in r.json()


class TestApiNorms:
    def test_post_norm_200(self, client):
        r = client.post(
            "/norm",
            json={
                "name": "no-attack",
                "description": "No attacking",
                "condition": "safe_zone",
                "prohibited": "attack",
            },
        )
        assert r.status_code == 200

    def test_post_norm_returns_id(self, client):
        r = client.post(
            "/norm",
            json={
                "name": "no-attack",
                "description": "No attacking",
                "condition": "safe_zone",
                "prohibited": "attack",
            },
        )
        data = r.json()
        assert "id" in data
        assert len(data["id"]) == 16

    def test_get_norms_200(self, client):
        r = client.get("/norms")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestApiCheck:
    def test_post_check_200(self, client):
        client.post(
            "/norm",
            json={
                "name": "no-attack",
                "description": "No attacking",
                "condition": "safe_zone",
                "prohibited": "attack",
            },
        )
        r = client.post(
            "/check",
            json={
                "agent_id": "agent1",
                "action": "attack",
                "location": "safe_zone",
            },
        )
        assert r.status_code == 200

    def test_post_check_violation(self, client):
        client.post(
            "/norm",
            json={
                "name": "no-attack",
                "description": "No attacking",
                "condition": "safe_zone",
                "prohibited": "attack",
            },
        )
        r = client.post(
            "/check",
            json={
                "agent_id": "agent1",
                "action": "attack",
                "location": "safe_zone",
            },
        )
        data = r.json()
        assert data["has_violations"] is True

    def test_post_check_no_violation(self, client):
        client.post(
            "/norm",
            json={
                "name": "no-attack",
                "description": "No attacking",
                "condition": "safe_zone",
                "prohibited": "attack",
            },
        )
        r = client.post(
            "/check",
            json={
                "agent_id": "agent1",
                "action": "trade",
                "location": "safe_zone",
            },
        )
        data = r.json()
        assert data["has_violations"] is False


class TestApiViolations:
    def test_get_violations_200(self, client):
        r = client.get("/violations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
