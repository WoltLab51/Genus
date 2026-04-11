"""Unit tests for ResponsePolicy building — Phase 14."""

import pytest

from genus.identity.models import PrivacyLevel, RoomContext, SystemRole, UserProfile
from genus.identity.permission_engine import PermissionEngine
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path) -> ProfileStore:
    s = ProfileStore(base_dir=tmp_path / "profiles")
    # Main user
    p = UserProfile(
        user_id="main_user",
        display_name="Main",
        system_role=SystemRole.ADULT,
        known_devices=["mains_handy"],
    )
    await s.save(p)
    # Child user
    from genus.identity.models import ChildSettings
    child = UserProfile(
        user_id="child_user",
        display_name="Kind",
        system_role=SystemRole.CHILD,
        child_settings=ChildSettings(),
    )
    await s.save(child)
    return s


@pytest.fixture
def engine(store) -> PermissionEngine:
    return PermissionEngine(store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResponsePolicyAlone:
    async def test_alone_with_public_content_allows_aloud(self, engine):
        ctx = RoomContext(room_id="wohnzimmer", present_user_ids=["main_user"])
        policy = await engine.build_response_policy("main_user", ctx, PrivacyLevel.PUBLIC)
        assert policy.may_answer_aloud is True
        assert policy.may_show_on_display is True

    async def test_no_context_allows_aloud(self, engine):
        policy = await engine.build_response_policy("main_user", None, PrivacyLevel.PERSONAL)
        assert policy.may_answer_aloud is True


class TestResponsePolicyChildren:
    async def test_child_present_personal_redirects(self, engine):
        ctx = RoomContext(
            room_id="wohnzimmer",
            present_user_ids=["main_user", "child_user"],
        )
        policy = await engine.build_response_policy("main_user", ctx, PrivacyLevel.PERSONAL)
        assert policy.may_answer_aloud is False
        assert policy.may_show_on_display is False
        assert policy.redirect_to_device == "mains_handy"

    async def test_child_present_public_content_ok(self, engine):
        ctx = RoomContext(
            room_id="wohnzimmer",
            present_user_ids=["main_user", "child_user"],
        )
        policy = await engine.build_response_policy("main_user", ctx, PrivacyLevel.PUBLIC)
        assert policy.may_answer_aloud is True


class TestResponsePolicyGuests:
    async def test_guests_restrict_to_public_only(self, engine):
        ctx = RoomContext(
            room_id="wohnzimmer",
            present_user_ids=["main_user"],
            guest_count=2,
        )
        policy = await engine.build_response_policy("main_user", ctx, PrivacyLevel.PERSONAL)
        assert policy.may_answer_aloud is False
        assert policy.max_privacy_level == PrivacyLevel.PUBLIC

    async def test_guests_with_public_content_is_ok(self, engine):
        ctx = RoomContext(
            room_id="wohnzimmer",
            present_user_ids=["main_user"],
            guest_count=1,
        )
        policy = await engine.build_response_policy("main_user", ctx, PrivacyLevel.PUBLIC)
        assert policy.may_answer_aloud is True


class TestResponsePolicyNSFW:
    async def test_nsfw_never_aloud_never_display(self, engine):
        policy = await engine.build_response_policy(
            "main_user", None, PrivacyLevel.NSFW
        )
        assert policy.may_answer_aloud is False
        assert policy.may_show_on_display is False

    async def test_nsfw_redirects_to_device(self, engine):
        policy = await engine.build_response_policy(
            "main_user", None, PrivacyLevel.NSFW
        )
        assert policy.redirect_to_device == "mains_handy"


class TestResponsePolicyConfidential:
    async def test_confidential_never_aloud(self, engine):
        policy = await engine.build_response_policy(
            "main_user", None, PrivacyLevel.CONFIDENTIAL
        )
        assert policy.may_answer_aloud is False
        assert policy.may_show_on_display is False
