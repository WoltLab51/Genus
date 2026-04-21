"""Unit tests for GET/POST /v1/agents/ API endpoints.

Tests cover:
- GET /v1/agents/ — list all agents
- GET /v1/agents/{agent_id}/status — single agent status
- POST /v1/agents/{agent_id}/invoke — invoke agent
- 401 auth guard (unauthenticated requests)
- 404 for unknown agent_id
- 503 when registry is not configured
"""

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.functional_agents import (
    FunctionalAgentRegistry,
    HomeAgent,
    FamilyAgent,
)

TEST_KEY = "test-api-key"
AUTH = {"Authorization": f"Bearer {TEST_KEY}"}


def _make_client(with_registry: bool = True):
    """Return a TestClient with optional FunctionalAgentRegistry."""
    app = create_app(api_key=TEST_KEY)
    if with_registry:
        reg = FunctionalAgentRegistry()
        reg.register(HomeAgent())
        reg.register(FamilyAgent())
        app.state.functional_agent_registry = reg
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


class TestAgentsAuth:
    def test_list_agents_no_auth_returns_401(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/")
        assert resp.status_code == 401

    def test_status_no_auth_returns_401(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/home/status")
        assert resp.status_code == 401

    def test_invoke_no_auth_returns_401(self):
        with _make_client() as client:
            resp = client.post("/v1/agents/home/invoke", json={"intent": "test"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/agents/
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_returns_200(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/", headers=AUTH)
        assert resp.status_code == 200

    def test_returns_list(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/", headers=AUTH)
        data = resp.json()
        assert isinstance(data, list)

    def test_contains_registered_agents(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/", headers=AUTH)
        ids = {a["agent_id"] for a in resp.json()}
        assert "home" in ids
        assert "family" in ids

    def test_each_entry_has_required_fields(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/", headers=AUTH)
        for entry in resp.json():
            assert "agent_id" in entry
            assert "role" in entry
            assert "description" in entry
            assert "ready" in entry

    def test_returns_503_when_no_registry(self):
        with _make_client(with_registry=False) as client:
            resp = client.get("/v1/agents/", headers=AUTH)
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /v1/agents/{agent_id}/status
# ---------------------------------------------------------------------------


class TestAgentStatus:
    def test_returns_200_for_existing_agent(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/home/status", headers=AUTH)
        assert resp.status_code == 200

    def test_returns_correct_agent_id(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/home/status", headers=AUTH)
        assert resp.json()["agent_id"] == "home"

    def test_returns_404_for_unknown_agent(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/unknown-xyz/status", headers=AUTH)
        assert resp.status_code == 404

    def test_family_agent_status(self):
        with _make_client() as client:
            resp = client.get("/v1/agents/family/status", headers=AUTH)
        data = resp.json()
        assert data["agent_id"] == "family"
        assert data["role"] == "family_management"


# ---------------------------------------------------------------------------
# POST /v1/agents/{agent_id}/invoke
# ---------------------------------------------------------------------------


class TestInvokeAgent:
    def test_returns_200(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Licht einschalten"},
                headers=AUTH,
            )
        assert resp.status_code == 200

    def test_response_has_agent_id(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Licht einschalten"},
                headers=AUTH,
            )
        data = resp.json()
        assert data["agent_id"] == "home"

    def test_response_has_text(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Licht einschalten"},
                headers=AUTH,
            )
        data = resp.json()
        assert isinstance(data["text"], str)
        assert len(data["text"]) > 0

    def test_response_success_is_true(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Heizung regulieren"},
                headers=AUTH,
            )
        assert resp.json()["success"] is True

    def test_invoke_unknown_agent_returns_404(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/nonexistent/invoke",
                json={"intent": "Test"},
                headers=AUTH,
            )
        assert resp.status_code == 404

    def test_user_id_defaults_to_anonymous(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Licht an"},
                headers=AUTH,
            )
        data = resp.json()
        assert data["data"]["user_id"] == "anonymous"

    def test_user_id_from_body(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Licht an", "user_id": "papa"},
                headers=AUTH,
            )
        assert resp.json()["data"]["user_id"] == "papa"

    def test_family_agent_invoke(self):
        with _make_client() as client:
            resp = client.post(
                "/v1/agents/family/invoke",
                json={"intent": "Termin eintragen"},
                headers=AUTH,
            )
        data = resp.json()
        assert data["agent_id"] == "family"
        assert resp.status_code == 200

    def test_invoke_503_when_no_registry(self):
        with _make_client(with_registry=False) as client:
            resp = client.post(
                "/v1/agents/home/invoke",
                json={"intent": "Test"},
                headers=AUTH,
            )
        assert resp.status_code == 503
