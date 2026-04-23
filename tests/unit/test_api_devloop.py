"""Unit tests for POST /v1/devloop/run API endpoint.

Covers:
- Successful run → status "completed"
- No Bearer token → 401
- Reader token (insufficient scope) → 403
- Kill-switch active → 503
- Orchestrator timeout → status "failed"
- Missing / empty goal → 422
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.dev.runtime import DevResponseTimeoutError
from genus.security.kill_switch import KillSwitch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPERATOR_KEY = "test-operator-key"
READER_KEY = "test-reader-key"
OPERATOR_AUTH = {"Authorization": f"Bearer {OPERATOR_KEY}"}
READER_AUTH = {"Authorization": f"Bearer {READER_KEY}"}

VALID_BODY = {"goal": "implement a hello-world function"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(kill_switch: KillSwitch | None = None):
    """Return a TestClient with operator and reader keys configured."""
    app = create_app(
        operator_key=OPERATOR_KEY,
        reader_key=READER_KEY,
        kill_switch=kill_switch,
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDevloopRunSuccess:
    def test_returns_200(self):
        """Successful run returns HTTP 200."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        assert resp.status_code == 200

    def test_status_is_completed(self):
        """Successful run returns status "completed"."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        data = resp.json()
        assert data["status"] == "completed"

    def test_response_contains_run_id(self):
        """Response contains a non-empty run_id."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        data = resp.json()
        assert data["run_id"]

    def test_custom_run_id_is_preserved(self):
        """Custom run_id in request body is reflected in the response."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client() as client:
                resp = client.post(
                    "/v1/devloop/run",
                    json={**VALID_BODY, "run_id": "my-custom-run"},
                    headers=OPERATOR_AUTH,
                )
        assert resp.json()["run_id"] == "my-custom-run"

    def test_phases_listed(self):
        """Successful response lists the traversed phases."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        data = resp.json()
        assert isinstance(data["phases"], list)
        assert len(data["phases"]) > 0


class TestDevloopRunUnauthorized:
    def test_no_bearer_token_returns_401(self):
        """Request without Authorization header returns 401."""
        with _make_client() as client:
            resp = client.post("/v1/devloop/run", json=VALID_BODY)
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self):
        """Request with invalid key returns 401."""
        with _make_client() as client:
            resp = client.post(
                "/v1/devloop/run",
                json=VALID_BODY,
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401


class TestDevloopRunWrongScope:
    def test_reader_token_returns_403(self):
        """Reader token (insufficient scope) returns 403."""
        with _make_client() as client:
            resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=READER_AUTH)
        assert resp.status_code == 403


class TestDevloopRunKillSwitchActive:
    def test_kill_switch_active_returns_503(self):
        """Active kill-switch returns 503 before attempting the run."""
        ks = KillSwitch()
        ks.activate(reason="maintenance", actor="test")
        with _make_client(kill_switch=ks) as client:
            resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        assert resp.status_code == 503

    def test_kill_switch_inactive_does_not_block(self):
        """Inactive kill-switch does not block the request."""
        ks = KillSwitch()  # inactive by default
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = None
            with _make_client(kill_switch=ks) as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        assert resp.status_code == 200


class TestDevloopRunTimeout:
    def test_timeout_returns_failed_status(self):
        """Orchestrator timeout returns status "failed" (not a 5xx error)."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = DevResponseTimeoutError(
                run_id="r1", phase_id="plan-1", timeout_s=5.0
            )
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"

    def test_timeout_response_contains_run_id(self):
        """Timeout response still includes a run_id."""
        with patch(
            "genus.dev.devloop_orchestrator.DevLoopOrchestrator.run",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = DevResponseTimeoutError(
                run_id="r1", phase_id="plan-1", timeout_s=5.0
            )
            with _make_client() as client:
                resp = client.post("/v1/devloop/run", json=VALID_BODY, headers=OPERATOR_AUTH)
        assert resp.json()["run_id"]


class TestDevloopRunMissingGoal:
    def test_empty_goal_returns_422(self):
        """Empty goal string (min_length=1) returns 422 Unprocessable Entity."""
        with _make_client() as client:
            resp = client.post(
                "/v1/devloop/run",
                json={"goal": ""},
                headers=OPERATOR_AUTH,
            )
        assert resp.status_code == 422

    def test_missing_goal_returns_422(self):
        """Request body without goal field returns 422."""
        with _make_client() as client:
            resp = client.post(
                "/v1/devloop/run",
                json={},
                headers=OPERATOR_AUTH,
            )
        assert resp.status_code == 422
