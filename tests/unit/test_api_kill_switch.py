"""
Unit tests for GENUS Kill-Switch API Endpoints (Phase 2)

Covers:
- GET /kill-switch/status without Auth → 401
- GET /kill-switch/status with Auth, no KillSwitch configured → {"active": false}
- GET /kill-switch/status with Auth, KillSwitch active → {"active": true, "reason": "..."}
- POST /kill-switch/activate without Auth → 401
- POST /kill-switch/activate with Auth + reason → 200, KillSwitch is active afterward
- POST /kill-switch/deactivate with Auth → 200, KillSwitch is inactive afterward
- POST /kill-switch/activate without configured KillSwitch → 503
"""

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.security.kill_switch import KillSwitch


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-secret-key"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_KEY}"}


def make_client(kill_switch=None):
    """Return a TestClient with an optional KillSwitch instance."""
    app = create_app(api_key=TEST_API_KEY, kill_switch=kill_switch)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /kill-switch/status — auth
# ---------------------------------------------------------------------------


class TestKillSwitchStatusAuth:
    def test_status_without_auth_returns_401(self):
        with make_client() as client:
            resp = client.get("/kill-switch/status")
        assert resp.status_code == 401

    def test_status_without_auth_has_error_field(self):
        with make_client() as client:
            resp = client.get("/kill-switch/status")
        data = resp.json()
        assert data["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# GET /kill-switch/status — no kill-switch configured
# ---------------------------------------------------------------------------


class TestKillSwitchStatusNotConfigured:
    def test_status_no_kill_switch_returns_200(self):
        with make_client(kill_switch=None) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_status_no_kill_switch_active_is_false(self):
        with make_client(kill_switch=None) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["active"] is False

    def test_status_no_kill_switch_has_empty_reason(self):
        with make_client(kill_switch=None) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["reason"] == ""

    def test_status_no_kill_switch_actor_is_none(self):
        with make_client(kill_switch=None) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["actor"] is None


# ---------------------------------------------------------------------------
# GET /kill-switch/status — with active KillSwitch
# ---------------------------------------------------------------------------


class TestKillSwitchStatusActive:
    def test_status_with_active_kill_switch_returns_true(self):
        ks = KillSwitch()
        ks.activate(reason="emergency stop", actor="ops")
        with make_client(kill_switch=ks) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["active"] is True

    def test_status_with_active_kill_switch_has_reason(self):
        ks = KillSwitch()
        ks.activate(reason="emergency stop", actor="ops")
        with make_client(kill_switch=ks) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["reason"] == "emergency stop"

    def test_status_with_active_kill_switch_has_actor(self):
        ks = KillSwitch()
        ks.activate(reason="emergency stop", actor="ops")
        with make_client(kill_switch=ks) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["actor"] == "ops"

    def test_status_with_inactive_kill_switch_returns_false(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.get("/kill-switch/status", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["active"] is False


# ---------------------------------------------------------------------------
# POST /kill-switch/activate — auth
# ---------------------------------------------------------------------------


class TestKillSwitchActivateAuth:
    def test_activate_without_auth_returns_401(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.post(
                "/kill-switch/activate", json={"reason": "test"}
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /kill-switch/activate — happy path
# ---------------------------------------------------------------------------


class TestKillSwitchActivateHappyPath:
    def test_activate_returns_200(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.post(
                "/kill-switch/activate",
                json={"reason": "security incident"},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200

    def test_activate_response_status_is_activated(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.post(
                "/kill-switch/activate",
                json={"reason": "security incident"},
                headers=AUTH_HEADERS,
            )
        data = resp.json()
        assert data["status"] == "activated"

    def test_activate_response_active_is_true(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.post(
                "/kill-switch/activate",
                json={"reason": "security incident"},
                headers=AUTH_HEADERS,
            )
        data = resp.json()
        assert data["active"] is True

    def test_activate_actually_activates_kill_switch(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            client.post(
                "/kill-switch/activate",
                json={"reason": "test activation"},
                headers=AUTH_HEADERS,
            )
        assert ks.is_active() is True

    def test_activate_sets_reason_on_kill_switch(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            client.post(
                "/kill-switch/activate",
                json={"reason": "my reason"},
                headers=AUTH_HEADERS,
            )
        assert ks.reason == "my reason"

    def test_activate_with_actor_sets_actor_on_kill_switch(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            client.post(
                "/kill-switch/activate",
                json={"reason": "incident", "actor": "admin-user"},
                headers=AUTH_HEADERS,
            )
        assert ks.actor == "admin-user"


# ---------------------------------------------------------------------------
# POST /kill-switch/activate — no kill-switch configured
# ---------------------------------------------------------------------------


class TestKillSwitchActivateNotConfigured:
    def test_activate_without_kill_switch_returns_503(self):
        with make_client(kill_switch=None) as client:
            resp = client.post(
                "/kill-switch/activate",
                json={"reason": "test"},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /kill-switch/deactivate — happy path
# ---------------------------------------------------------------------------


class TestKillSwitchDeactivateHappyPath:
    def test_deactivate_returns_200(self):
        ks = KillSwitch()
        ks.activate(reason="prior activation")
        with make_client(kill_switch=ks) as client:
            resp = client.post("/kill-switch/deactivate", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_deactivate_response_status_is_deactivated(self):
        ks = KillSwitch()
        ks.activate(reason="prior activation")
        with make_client(kill_switch=ks) as client:
            resp = client.post("/kill-switch/deactivate", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["status"] == "deactivated"

    def test_deactivate_response_active_is_false(self):
        ks = KillSwitch()
        ks.activate(reason="prior activation")
        with make_client(kill_switch=ks) as client:
            resp = client.post("/kill-switch/deactivate", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["active"] is False

    def test_deactivate_actually_deactivates_kill_switch(self):
        ks = KillSwitch()
        ks.activate(reason="prior activation")
        with make_client(kill_switch=ks) as client:
            client.post("/kill-switch/deactivate", headers=AUTH_HEADERS)
        assert ks.is_active() is False

    def test_deactivate_without_auth_returns_401(self):
        ks = KillSwitch()
        with make_client(kill_switch=ks) as client:
            resp = client.post("/kill-switch/deactivate")
        assert resp.status_code == 401

    def test_deactivate_without_kill_switch_returns_503(self):
        with make_client(kill_switch=None) as client:
            resp = client.post("/kill-switch/deactivate", headers=AUTH_HEADERS)
        assert resp.status_code == 503
