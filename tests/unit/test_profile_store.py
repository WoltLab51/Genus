"""Unit tests for ProfileStore — Phase 14."""

import pytest

from genus.identity.models import SystemRole, UserProfile
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path) -> ProfileStore:
    return ProfileStore(base_dir=tmp_path / "profiles")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProfileStoreBasics:
    async def test_save_and_load_are_identical(self, store):
        original = UserProfile(
            user_id="test_user",
            display_name="Test User",
            system_role=SystemRole.ADULT,
        )
        await store.save(original)
        loaded = await store.get("test_user")
        assert loaded is not None
        assert loaded.user_id == original.user_id
        assert loaded.display_name == original.display_name
        assert loaded.system_role == original.system_role

    async def test_missing_profile_returns_none(self, store):
        result = await store.get("nonexistent_user")
        assert result is None

    async def test_exists_returns_false_for_missing(self, store):
        assert await store.exists("ghost") is False

    async def test_exists_returns_true_after_save(self, store):
        p = UserProfile(user_id="present", display_name="Present")
        await store.save(p)
        assert await store.exists("present") is True

    async def test_list_all_returns_saved_profiles(self, store):
        for i in range(3):
            await store.save(UserProfile(user_id=f"user_{i}", display_name=f"User {i}"))
        all_profiles = await store.list_all()
        assert len(all_profiles) == 3

    async def test_save_overwrites_existing(self, store):
        p = UserProfile(user_id="overwrite_me", display_name="Old Name")
        await store.save(p)
        p2 = p.model_copy(update={"display_name": "New Name"})
        await store.save(p2)
        loaded = await store.get("overwrite_me")
        assert loaded.display_name == "New Name"


class TestSuperadmin:
    async def test_get_or_create_superadmin_creates_on_first_call(self, store):
        profile = await store.get_or_create_superadmin()
        assert profile.user_id == "ronny_wolter"
        assert profile.system_role == SystemRole.SUPERADMIN
        assert profile.is_developer is True
        assert profile.is_operator is True
        assert profile.onboarding_complete is True

    async def test_get_or_create_superadmin_idempotent(self, store):
        p1 = await store.get_or_create_superadmin()
        p2 = await store.get_or_create_superadmin()
        assert p1.user_id == p2.user_id
        # Should be the same (not reset fields)
        assert p1.system_role == p2.system_role


class TestCanUseAgent:
    async def test_superadmin_can_use_any_agent(self, store):
        profile = await store.get_or_create_superadmin()
        assert profile.can_use_agent("trading_agent") is True
        assert profile.can_use_agent("secret_agent") is True

    async def test_adult_no_restrictions_can_use_any(self, store):
        p = UserProfile(
            user_id="free_adult",
            display_name="Free",
            system_role=SystemRole.ADULT,
            allowed_agents=None,
        )
        assert p.can_use_agent("anything") is True

    async def test_adult_denied_agent_blocked(self, store):
        p = UserProfile(
            user_id="restricted",
            display_name="Restricted",
            system_role=SystemRole.ADULT,
            denied_agents=["nsfw_agent"],
        )
        assert p.can_use_agent("nsfw_agent") is False

    async def test_child_only_whitelist_allowed(self, store):
        from genus.identity.models import ChildSettings
        p = UserProfile(
            user_id="kind",
            display_name="Kind",
            system_role=SystemRole.CHILD,
            child_settings=ChildSettings(allowed_agents=["dnd_master"]),
        )
        assert p.can_use_agent("dnd_master") is True
        assert p.can_use_agent("trading_agent") is False
