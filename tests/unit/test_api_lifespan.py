"""
Unit tests for GENUS API Lifespan, agent wiring, and KillSwitch consistency.

Covers:
- create_app(use_lifespan=False) — no regression on existing behaviour
- GET /health reachable after startup (use_lifespan=False)
- POST /runs with message_bus=None → 200, run_id in response (silent, no bus)
- POST /runs with real MessageBus (injected) → run.started published
- assert_kill_switch_consistent with same instance → no error
- assert_kill_switch_consistent with different instances → RuntimeError
- assert_kill_switch_consistent when either is None → no error
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.api.deps import assert_kill_switch_consistent
from genus.communication.message_bus import MessageBus
from genus.run.topics import RUN_STARTED
from genus.security.kill_switch import KillSwitch


# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-secret-key"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY}"}


def make_bus_spy():
    """Return a mock MessageBus that records published messages."""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


def make_client(bus=None, kill_switch=None, use_lifespan=False):
    """Return a TestClient with the given configuration."""
    app = create_app(
        api_key=TEST_API_KEY,
        message_bus=bus,
        kill_switch=kill_switch,
        use_lifespan=use_lifespan,
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# create_app(use_lifespan=False) — no regression
# ---------------------------------------------------------------------------


class TestCreateAppNoLifespan:
    def test_use_lifespan_false_is_default(self):
        """create_app without use_lifespan should behave identically to before."""
        app = create_app(api_key=TEST_API_KEY)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_use_lifespan_false_explicit(self):
        """create_app(use_lifespan=False) should start without errors."""
        app = create_app(api_key=TEST_API_KEY, use_lifespan=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_injected_message_bus_still_works(self):
        """Injected message_bus should still be used when use_lifespan=False."""
        bus = make_bus_spy()
        with make_client(bus=bus, use_lifespan=False) as client:
            client.post("/runs", json={"goal": "test"}, headers=AUTH_HEADERS)
        bus.publish.assert_called_once()

    def test_injected_kill_switch_still_works(self):
        """Injected kill_switch should still be accessible when use_lifespan=False."""
        ks = KillSwitch()
        with make_client(kill_switch=ks, use_lifespan=False) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /health reachable
# ---------------------------------------------------------------------------


class TestHealthAfterStartup:
    def test_health_returns_200_with_lifespan_false(self):
        with make_client() as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status_with_lifespan_false(self):
        with make_client() as client:
            resp = client.get("/health")
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /runs with message_bus=None → silent, returns 200 with run_id
# ---------------------------------------------------------------------------


class TestRunsWithNoBus:
    def test_post_runs_without_bus_returns_200(self):
        """POST /runs with no message_bus should not crash — bus publish is skipped."""
        with make_client(bus=None) as client:
            resp = client.post(
                "/runs",
                json={"goal": "silent run"},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200

    def test_post_runs_without_bus_has_run_id(self):
        with make_client(bus=None) as client:
            resp = client.post(
                "/runs",
                json={"goal": "silent run"},
                headers=AUTH_HEADERS,
            )
        data = resp.json()
        assert "run_id" in data
        assert data["run_id"]

    def test_post_runs_without_bus_has_started_status(self):
        with make_client(bus=None) as client:
            resp = client.post(
                "/runs",
                json={"goal": "silent run"},
                headers=AUTH_HEADERS,
            )
        assert resp.json()["status"] == "started"


# ---------------------------------------------------------------------------
# POST /runs with real MessageBus (injected) → run.started published
# ---------------------------------------------------------------------------


class TestRunsWithRealBus:
    def test_post_runs_with_real_bus_publishes_run_started(self):
        """POST /runs with a real (mock) bus publishes run.started."""
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/runs",
                json={"goal": "wired run"},
                headers=AUTH_HEADERS,
            )
        bus.publish.assert_called_once()
        msg = bus.publish.call_args[0][0]
        assert msg.topic == RUN_STARTED

    def test_post_runs_published_message_has_goal(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/runs",
                json={"goal": "specific goal"},
                headers=AUTH_HEADERS,
            )
        msg = bus.publish.call_args[0][0]
        assert msg.payload["goal"] == "specific goal"

    def test_post_runs_published_message_has_run_id_in_metadata(self):
        bus = make_bus_spy()
        with make_client(bus=bus) as client:
            client.post(
                "/runs",
                json={"goal": "run id test", "run_id": "my-run-123"},
                headers=AUTH_HEADERS,
            )
        msg = bus.publish.call_args[0][0]
        assert msg.metadata.get("run_id") == "my-run-123"


# ---------------------------------------------------------------------------
# assert_kill_switch_consistent
# ---------------------------------------------------------------------------


class TestAssertKillSwitchConsistent:
    def test_same_instance_raises_no_error(self):
        """Same KillSwitch instance in both app.state and bus → no error."""
        ks = KillSwitch()
        bus = MessageBus(kill_switch=ks)

        app = create_app(api_key=TEST_API_KEY, message_bus=bus, kill_switch=ks)
        # Should not raise
        assert_kill_switch_consistent(app)

    def test_different_instances_raises_runtime_error(self):
        """Different KillSwitch instances in app.state and bus → RuntimeError."""
        ks1 = KillSwitch()
        ks2 = KillSwitch()
        bus = MessageBus(kill_switch=ks1)

        app = create_app(api_key=TEST_API_KEY, message_bus=bus, kill_switch=ks2)
        with pytest.raises(RuntimeError, match="KillSwitch mismatch"):
            assert_kill_switch_consistent(app)

    def test_no_kill_switch_in_state_raises_no_error(self):
        """app.state.kill_switch is None → no error."""
        bus = MessageBus()
        app = create_app(api_key=TEST_API_KEY, message_bus=bus, kill_switch=None)
        # Should not raise
        assert_kill_switch_consistent(app)

    def test_no_bus_in_state_raises_no_error(self):
        """app.state.message_bus is None → no error."""
        ks = KillSwitch()
        app = create_app(api_key=TEST_API_KEY, message_bus=None, kill_switch=ks)
        # Should not raise
        assert_kill_switch_consistent(app)

    def test_both_none_raises_no_error(self):
        """Both app.state.kill_switch and app.state.message_bus are None → no error."""
        app = create_app(api_key=TEST_API_KEY)
        # Should not raise
        assert_kill_switch_consistent(app)

    def test_bus_without_kill_switch_raises_no_error(self):
        """Bus has no kill_switch wired in, app state has one → no mismatch."""
        ks = KillSwitch()
        bus = MessageBus()  # no kill_switch
        app = create_app(api_key=TEST_API_KEY, message_bus=bus, kill_switch=ks)
        # bus._kill_switch is None, so no mismatch can be detected → no error
        assert_kill_switch_consistent(app)
