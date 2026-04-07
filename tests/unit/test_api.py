"""
Unit tests for GENUS API Layer (Phase 1)

Covers:
- GET /health → 200, {"status": "ok"}
- POST /runs without Auth → 401
- POST /runs with wrong key → 401
- POST /runs with correct key → 200, run_id in response
- POST /runs publishes run.started on MessageBus (MessageBus spy)
- POST /outcome without Auth → 401
- POST /outcome with correct key + valid payload → 200
- POST /outcome publishes outcome.recorded on MessageBus
- POST /outcome with invalid payload → 422
- Unknown route → 404
- Error in handler → 500 structured (no stack trace in body)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import APIRouter
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.run.topics import RUN_STARTED
from genus.feedback.topics import OUTCOME_RECORDED


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-secret-key"


def make_bus_spy():
    """Return a mock MessageBus that records published messages."""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


def make_client(bus=None):
    """Return a TestClient with an optional MessageBus spy."""
    app = create_app(api_key=TEST_API_KEY, message_bus=bus)
    return TestClient(app, raise_server_exceptions=False)


VALID_OUTCOME_BODY = {
    "outcome": "good",
    "score_delta": 1.0,
    "run_id": "run-abc-123",
}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self):
        with make_client() as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self):
        with make_client() as client:
            resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_no_auth_required(self):
        with make_client() as client:
            resp = client.get("/health")
        # No Authorization header — must still succeed
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /runs — auth checks
# ---------------------------------------------------------------------------


class TestRunsAuth:
    def test_runs_without_auth_returns_401(self):
        with make_client() as client:
            resp = client.post("/runs", json={"goal": "do something"})
        assert resp.status_code == 401

    def test_runs_with_wrong_key_returns_401(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "do something"},
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401

    def test_runs_401_response_has_error_field(self):
        with make_client() as client:
            resp = client.post("/runs", json={"goal": "do something"})
        data = resp.json()
        assert data["error"] == "unauthorized"

    def test_runs_with_correct_key_returns_200(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "do something"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /runs — happy path
# ---------------------------------------------------------------------------


class TestRunsHappyPath:
    def test_runs_response_contains_run_id(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "build a feature"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert "run_id" in data

    def test_runs_response_status_is_started(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "build a feature"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert data["status"] == "started"

    def test_runs_uses_provided_run_id(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "task", "run_id": "my-custom-run-id"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert data["run_id"] == "my-custom-run-id"

    def test_runs_generates_run_id_when_absent(self):
        with make_client() as client:
            resp = client.post(
                "/runs",
                json={"goal": "another task"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert data["run_id"]  # non-empty string

    def test_runs_publishes_run_started_on_bus(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/runs",
                json={"goal": "publish test"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        bus.publish.assert_called_once()
        published_msg = bus.publish.call_args[0][0]
        assert published_msg.topic == RUN_STARTED

    def test_runs_published_message_contains_goal(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/runs",
                json={"goal": "my specific goal"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        published_msg = bus.publish.call_args[0][0]
        assert published_msg.payload["goal"] == "my specific goal"


# ---------------------------------------------------------------------------
# /outcome — auth checks
# ---------------------------------------------------------------------------


class TestOutcomeAuth:
    def test_outcome_without_auth_returns_401(self):
        with make_client() as client:
            resp = client.post("/outcome", json=VALID_OUTCOME_BODY)
        assert resp.status_code == 401

    def test_outcome_with_correct_key_returns_200(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json=VALID_OUTCOME_BODY,
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /outcome — happy path
# ---------------------------------------------------------------------------


class TestOutcomeHappyPath:
    def test_outcome_response_status_is_recorded(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json=VALID_OUTCOME_BODY,
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert data["status"] == "recorded"

    def test_outcome_response_contains_run_id(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json=VALID_OUTCOME_BODY,
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        data = resp.json()
        assert data["run_id"] == "run-abc-123"

    def test_outcome_publishes_outcome_recorded_on_bus(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/outcome",
                json=VALID_OUTCOME_BODY,
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        bus.publish.assert_called_once()
        published_msg = bus.publish.call_args[0][0]
        assert published_msg.topic == OUTCOME_RECORDED

    def test_outcome_published_message_contains_outcome(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/outcome",
                json=VALID_OUTCOME_BODY,
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        published_msg = bus.publish.call_args[0][0]
        assert published_msg.payload["outcome"] == "good"


# ---------------------------------------------------------------------------
# /outcome — validation
# ---------------------------------------------------------------------------


class TestOutcomeValidation:
    def test_outcome_missing_required_field_returns_422(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json={"score_delta": 1.0},  # missing "outcome"
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 422

    def test_outcome_invalid_outcome_value_returns_422(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json={"outcome": "invalid", "score_delta": 1.0},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 422

    def test_outcome_non_numeric_score_delta_returns_422(self):
        with make_client() as client:
            resp = client.post(
                "/outcome",
                json={"outcome": "good", "score_delta": "not-a-number"},
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Unknown routes
# ---------------------------------------------------------------------------


class TestUnknownRoute:
    def test_unknown_route_returns_404(self):
        # Middleware runs before routing; provide a valid key so routing is reached
        with make_client() as client:
            resp = client.get(
                "/does-not-exist",
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_500_returns_structured_json(self):
        """An exception in a handler must produce structured JSON, not a stack trace."""
        bad_router = APIRouter()

        @bad_router.get("/boom")
        async def boom():
            raise RuntimeError("Something went wrong internally")

        error_app = create_app(api_key=TEST_API_KEY)
        error_app.router.routes.clear()
        error_app.include_router(bad_router)

        with TestClient(error_app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/boom", headers={"Authorization": f"Bearer {TEST_API_KEY}"}
            )
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "internal_error"
        # No stack trace in response body
        assert "Traceback" not in resp.text
