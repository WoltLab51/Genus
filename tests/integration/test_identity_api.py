"""Integration tests for Identity API endpoints — Phase 14."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient, ASGITransport

from genus.api.app import create_app
from genus.identity.group_store import GroupStore
from genus.identity.models import SystemRole, UserProfile
from genus.identity.permission_engine import PermissionEngine
from genus.identity.privacy_vault import PrivacyVault
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Test setup
# ---------------------------------------------------------------------------

ADMIN_KEY = "test-admin-key-phase14"


def _make_bus():
    from genus.communication.message_bus import MessageBus
    bus = MagicMock(spec=MessageBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
async def app_with_identity(tmp_path, monkeypatch):
    """Create app with identity stores injected into app.state."""
    monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)

    profile_store = ProfileStore(base_dir=tmp_path / "profiles")
    group_store = GroupStore(base_dir=tmp_path / "groups")
    permission_engine = PermissionEngine(profile_store)
    privacy_vault = PrivacyVault(base_dir=tmp_path / "vault", profile_store=profile_store)

    # Create superadmin profile
    await profile_store.get_or_create_superadmin()

    # Create a regular user
    adult = UserProfile(
        user_id="adult_user",
        display_name="Adult User",
        system_role=SystemRole.ADULT,
        onboarding_complete=True,
    )
    await profile_store.save(adult)

    # Create a child user
    from genus.identity.models import ChildSettings
    child = UserProfile(
        user_id="child_user",
        display_name="Kind A",
        system_role=SystemRole.CHILD,
        onboarding_complete=True,
        child_settings=ChildSettings(),
    )
    await profile_store.save(child)

    app = create_app(admin_key=ADMIN_KEY)
    app.state.profile_store = profile_store
    app.state.group_store = group_store
    app.state.permission_engine = permission_engine
    app.state.privacy_vault = privacy_vault

    # Set up parental agent mock
    from genus.agents.parental_agent import ParentalAgent
    bus = _make_bus()
    parental_agent = ParentalAgent(message_bus=bus, profile_store=profile_store)
    await parental_agent.initialize()
    await parental_agent.start()
    app.state.parental_agent = parental_agent

    return app, profile_store, group_store


@pytest.fixture
async def client(app_with_identity):
    app, _, _ = app_with_identity
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetMyProfile:
    async def test_get_me_superadmin(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        response = await client.get("/me")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "ronny_wolter"
        assert data["system_role"] == "superadmin"

    async def test_get_me_without_auth_returns_401(self, app_with_identity):
        app, _, _ = app_with_identity
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            response = await c.get("/me")
        assert response.status_code == 401


class TestUpdateMyProfile:
    async def test_put_me_updates_display_name(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        response = await client.put("/me", json={"display_name": "Ronny Updated"})
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Ronny Updated"

    async def test_put_me_updates_language(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        response = await client.put("/me", json={"preferred_language": "en"})
        assert response.status_code == 200
        assert response.json()["preferred_language"] == "en"


class TestGetMyPermissions:
    async def test_get_permissions_returns_role(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        response = await client.get("/me/permissions")
        assert response.status_code == 200
        data = response.json()
        assert data["system_role"] == "superadmin"


class TestGroups:
    async def test_create_and_list_groups(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        # Create group
        resp = await client.post("/groups", json={"name": "Test Group", "group_type": "family"})
        assert resp.status_code == 201
        group_id = resp.json()["group_id"]

        # List groups
        resp2 = await client.get("/groups")
        assert resp2.status_code == 200
        group_ids = [g["group_id"] for g in resp2.json()]
        assert group_id in group_ids

    async def test_get_group_details(self, client, monkeypatch):
        monkeypatch.setenv("GENUS_MASTER_KEY", ADMIN_KEY)
        resp = await client.post("/groups", json={"name": "My Group"})
        group_id = resp.json()["group_id"]
        resp2 = await client.get(f"/groups/{group_id}")
        assert resp2.status_code == 200
        assert resp2.json()["group_id"] == group_id

    async def test_get_nonexistent_group_returns_404(self, client):
        resp = await client.get("/groups/ghost_group_id")
        assert resp.status_code == 404


class TestUserManagement:
    async def test_list_users_as_admin(self, client):
        resp = await client.get("/users")
        assert resp.status_code == 200
        user_ids = [u["user_id"] for u in resp.json()]
        assert "ronny_wolter" in user_ids

    async def test_get_specific_user(self, client):
        resp = await client.get("/users/adult_user")
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "adult_user"

    async def test_get_nonexistent_user_returns_404(self, client):
        resp = await client.get("/users/ghost_user")
        assert resp.status_code == 404

    async def test_set_user_permissions(self, client):
        resp = await client.put(
            "/users/adult_user/permissions",
            json={"denied_agents": ["trading_agent"]},
        )
        assert resp.status_code == 200
        assert "trading_agent" in resp.json()["denied_agents"]

    async def test_child_cannot_list_users(self, app_with_identity):
        """Non-admin role gets 403 on /users."""
        app, _, _ = app_with_identity
        app2 = create_app(reader_key="reader-key")
        app2.state.profile_store = app.state.profile_store
        app2.state.group_store = app.state.group_store
        app2.state.permission_engine = app.state.permission_engine
        app2.state.privacy_vault = app.state.privacy_vault
        app2.state.parental_agent = app.state.parental_agent
        async with AsyncClient(
            transport=ASGITransport(app=app2),
            base_url="http://test",
            headers={"Authorization": "Bearer reader-key"},
        ) as c:
            resp = await c.get("/users")
        assert resp.status_code == 403


class TestParentalReport:
    async def test_parental_report_for_child(self, client):
        resp = await client.get("/parental/report/child_user")
        assert resp.status_code == 200
        data = resp.json()
        assert "child" in data
        assert "screen_time_minutes" in data


class TestLockUnlock:
    async def test_lock_and_unlock_user(self, client):
        resp = await client.post("/users/adult_user/lock")
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"

        resp2 = await client.post("/users/adult_user/unlock")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "unlocked"
