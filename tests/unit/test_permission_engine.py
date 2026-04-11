"""Unit tests for PermissionEngine — Phase 14."""

import pytest

from genus.identity.models import ChildSettings, SystemRole, UserProfile
from genus.identity.permission_engine import PermissionEngine
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def tmp_profile_store(tmp_path):
    return ProfileStore(base_dir=tmp_path / "profiles")


@pytest.fixture
async def engine(tmp_profile_store):
    return PermissionEngine(tmp_profile_store)


async def _save(store: ProfileStore, **kwargs) -> UserProfile:
    p = UserProfile(**kwargs)
    await store.save(p)
    return p


# ---------------------------------------------------------------------------
# SUPERADMIN tests
# ---------------------------------------------------------------------------


class TestSuperadmin:
    async def test_superadmin_may_use_any_agent(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="ronny_wolter",
            display_name="Ronny",
            system_role=SystemRole.SUPERADMIN,
        )
        allowed, reason = await engine.can_use_agent("ronny_wolter", "trading_agent")
        assert allowed is True
        assert reason == "superadmin"

    async def test_superadmin_may_use_restricted_agent(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="ronny_wolter",
            display_name="Ronny",
            system_role=SystemRole.SUPERADMIN,
            denied_agents=["top_secret"],
        )
        allowed, _ = await engine.can_use_agent("ronny_wolter", "top_secret")
        assert allowed is True  # superadmin ignores denied_agents


# ---------------------------------------------------------------------------
# CHILD tests
# ---------------------------------------------------------------------------


class TestChild:
    async def test_child_blocked_from_trading(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="kind_a",
            display_name="Kind A",
            system_role=SystemRole.CHILD,
            child_settings=ChildSettings(
                allowed_agents=["conversation", "dnd_master"]
            ),
        )
        allowed, reason = await engine.can_use_agent("kind_a", "trading_agent")
        assert allowed is False
        assert "child" in reason.lower()

    async def test_child_allowed_for_dnd_master(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="kind_a",
            display_name="Kind A",
            system_role=SystemRole.CHILD,
            child_settings=ChildSettings(
                allowed_agents=["conversation", "dnd_master"]
            ),
        )
        allowed, reason = await engine.can_use_agent("kind_a", "dnd_master")
        assert allowed is True
        assert "whitelist" in reason.lower()

    async def test_child_without_settings_denied(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="kind_b",
            display_name="Kind B",
            system_role=SystemRole.CHILD,
            child_settings=None,
        )
        allowed, reason = await engine.can_use_agent("kind_b", "any_agent")
        assert allowed is False


# ---------------------------------------------------------------------------
# ADULT tests
# ---------------------------------------------------------------------------


class TestAdult:
    async def test_adult_with_no_restrictions_allowed(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="adult_user",
            display_name="Adult",
            system_role=SystemRole.ADULT,
            allowed_agents=None,
        )
        allowed, reason = await engine.can_use_agent("adult_user", "any_agent")
        assert allowed is True
        assert "no restrictions" in reason

    async def test_adult_explicitly_denied(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="adult_user",
            display_name="Adult",
            system_role=SystemRole.ADULT,
            denied_agents=["secret_agent"],
        )
        allowed, reason = await engine.can_use_agent("adult_user", "secret_agent")
        assert allowed is False
        assert "denied" in reason

    async def test_adult_with_allowlist_denied_unlisted(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="adult_user",
            display_name="Adult",
            system_role=SystemRole.ADULT,
            allowed_agents=["agent_a"],
        )
        allowed, _ = await engine.can_use_agent("adult_user", "agent_b")
        assert allowed is False

    async def test_adult_with_allowlist_allowed_listed(self, tmp_profile_store, engine):
        await _save(
            tmp_profile_store,
            user_id="adult_user",
            display_name="Adult",
            system_role=SystemRole.ADULT,
            allowed_agents=["agent_a"],
        )
        allowed, _ = await engine.can_use_agent("adult_user", "agent_a")
        assert allowed is True


# ---------------------------------------------------------------------------
# Unknown user
# ---------------------------------------------------------------------------


class TestUnknownUser:
    async def test_unknown_user_denied(self, engine):
        allowed, reason = await engine.can_use_agent("ghost", "any_agent")
        assert allowed is False
        assert "unknown" in reason
