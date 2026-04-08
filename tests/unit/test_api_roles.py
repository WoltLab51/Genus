"""
Unit tests for GENUS API Role-Based Access Control

Covers the three-role model (admin / operator / reader) introduced in v1:
- admin_key   → role "admin"   — may do everything
- operator_key → role "operator" — may start runs, read status
- reader_key  → role "reader"  — read-only GET endpoints only
- unknown key → 401 Unauthorized

Endpoint matrix under test:
| Endpoint                      | Required role |
|-------------------------------|---------------|
| POST /kill-switch/activate    | admin         |
| POST /kill-switch/deactivate  | admin         |
| GET  /kill-switch/status      | reader+       |
| POST /runs                    | operator+     |
| GET  /runs/{run_id}           | reader+       |

Backward compatibility:
- Callers that pass only ``api_key`` to create_app() get admin role (darf alles).
"""

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.security.kill_switch import KillSwitch

# ---------------------------------------------------------------------------
# Fixed test keys
# ---------------------------------------------------------------------------

ADMIN_KEY = "admin-secret"
OPERATOR_KEY = "operator-secret"
READER_KEY = "reader-secret"
UNKNOWN_KEY = "not-a-valid-key"

ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_KEY}"}
OPERATOR_HEADERS = {"Authorization": f"Bearer {OPERATOR_KEY}"}
READER_HEADERS = {"Authorization": f"Bearer {READER_KEY}"}
UNKNOWN_HEADERS = {"Authorization": f"Bearer {UNKNOWN_KEY}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ks():
    return KillSwitch()


@pytest.fixture()
def client(ks):
    """TestClient with separate admin / operator / reader keys."""
    app = create_app(
        admin_key=ADMIN_KEY,
        operator_key=OPERATOR_KEY,
        reader_key=READER_KEY,
        kill_switch=ks,
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /kill-switch/activate — admin only
# ---------------------------------------------------------------------------


class TestKillSwitchActivateRoles:
    def test_admin_can_activate(self, client, ks):
        resp = client.post(
            "/kill-switch/activate",
            json={"reason": "test"},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert ks.is_active() is True

    def test_operator_cannot_activate(self, client):
        resp = client.post(
            "/kill-switch/activate",
            json={"reason": "test"},
            headers=OPERATOR_HEADERS,
        )
        assert resp.status_code == 403

    def test_reader_cannot_activate(self, client):
        resp = client.post(
            "/kill-switch/activate",
            json={"reason": "test"},
            headers=READER_HEADERS,
        )
        assert resp.status_code == 403

    def test_unknown_key_returns_401_on_activate(self, client):
        resp = client.post(
            "/kill-switch/activate",
            json={"reason": "test"},
            headers=UNKNOWN_HEADERS,
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /kill-switch/deactivate — admin only
# ---------------------------------------------------------------------------


class TestKillSwitchDeactivateRoles:
    def test_admin_can_deactivate(self, client, ks):
        ks.activate(reason="pre-activated")
        resp = client.post("/kill-switch/deactivate", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert ks.is_active() is False

    def test_operator_cannot_deactivate(self, client):
        resp = client.post("/kill-switch/deactivate", headers=OPERATOR_HEADERS)
        assert resp.status_code == 403

    def test_reader_cannot_deactivate(self, client):
        resp = client.post("/kill-switch/deactivate", headers=READER_HEADERS)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /kill-switch/status — reader+
# ---------------------------------------------------------------------------


class TestKillSwitchStatusRoles:
    def test_admin_can_read_status(self, client):
        resp = client.get("/kill-switch/status", headers=ADMIN_HEADERS)
        assert resp.status_code == 200

    def test_operator_can_read_status(self, client):
        resp = client.get("/kill-switch/status", headers=OPERATOR_HEADERS)
        assert resp.status_code == 200

    def test_reader_can_read_status(self, client):
        resp = client.get("/kill-switch/status", headers=READER_HEADERS)
        assert resp.status_code == 200

    def test_unknown_key_returns_401_on_status(self, client):
        resp = client.get("/kill-switch/status", headers=UNKNOWN_HEADERS)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /runs — operator+
# ---------------------------------------------------------------------------


class TestRunsRoles:
    def test_admin_can_start_run(self, client):
        resp = client.post("/runs", json={"goal": "test"}, headers=ADMIN_HEADERS)
        assert resp.status_code == 200

    def test_operator_can_start_run(self, client):
        resp = client.post("/runs", json={"goal": "test"}, headers=OPERATOR_HEADERS)
        assert resp.status_code == 200

    def test_reader_cannot_start_run(self, client):
        resp = client.post("/runs", json={"goal": "test"}, headers=READER_HEADERS)
        assert resp.status_code == 403

    def test_unknown_key_returns_401_on_runs(self, client):
        resp = client.post("/runs", json={"goal": "test"}, headers=UNKNOWN_HEADERS)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /runs/{run_id} — reader+
# ---------------------------------------------------------------------------


class TestRunGetRoles:
    """GET /runs/{run_id} requires reader role; 404 is acceptable (auth passed)."""

    def _expect_auth_ok(self, resp):
        """Assert that auth was accepted (status is NOT 401/403)."""
        assert resp.status_code not in (401, 403), (
            f"Expected auth to pass, got {resp.status_code}: {resp.text}"
        )

    def test_admin_can_get_run(self, client):
        resp = client.get("/runs/any-run-id", headers=ADMIN_HEADERS)
        self._expect_auth_ok(resp)

    def test_operator_can_get_run(self, client):
        resp = client.get("/runs/any-run-id", headers=OPERATOR_HEADERS)
        self._expect_auth_ok(resp)

    def test_reader_can_get_run(self, client):
        resp = client.get("/runs/any-run-id", headers=READER_HEADERS)
        self._expect_auth_ok(resp)

    def test_unknown_key_returns_401_on_run_get(self, client):
        resp = client.get("/runs/any-run-id", headers=UNKNOWN_HEADERS)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Backward compatibility — legacy api_key acts as admin
# ---------------------------------------------------------------------------


class TestLegacyApiKeyBackwardCompat:
    """A caller that passes only ``api_key`` to create_app() must still work."""

    LEGACY_KEY = "legacy-test-key"

    @pytest.fixture()
    def legacy_client(self):
        ks = KillSwitch()
        app = create_app(api_key=self.LEGACY_KEY, kill_switch=ks)
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, ks

    def test_legacy_key_can_activate_kill_switch(self, legacy_client):
        client, ks = legacy_client
        resp = client.post(
            "/kill-switch/activate",
            json={"reason": "legacy test"},
            headers={"Authorization": f"Bearer {self.LEGACY_KEY}"},
        )
        assert resp.status_code == 200
        assert ks.is_active() is True

    def test_legacy_key_can_start_run(self, legacy_client):
        client, _ = legacy_client
        resp = client.post(
            "/runs",
            json={"goal": "legacy goal"},
            headers={"Authorization": f"Bearer {self.LEGACY_KEY}"},
        )
        assert resp.status_code == 200

    def test_legacy_key_can_read_status(self, legacy_client):
        client, _ = legacy_client
        resp = client.get(
            "/kill-switch/status",
            headers={"Authorization": f"Bearer {self.LEGACY_KEY}"},
        )
        assert resp.status_code == 200

    def test_wrong_key_still_returns_401(self, legacy_client):
        client, _ = legacy_client
        resp = client.post(
            "/runs",
            json={"goal": "should fail"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401
