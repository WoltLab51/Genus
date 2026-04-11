"""Integration tests for OnboardingAgent — Phase 14."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genus.agents.parental_agent import ParentalAgent
from genus.communication.message_bus import MessageBus
from genus.identity.group_store import GroupStore
from genus.identity.onboarding_agent import OnboardingAgent
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bus():
    bus = MagicMock(spec=MessageBus)
    bus.publish = AsyncMock()
    return bus


async def _make_onboarding_agent(tmp_path):
    bus = _make_bus()
    profile_store = ProfileStore(base_dir=tmp_path / "profiles")
    group_store = GroupStore(base_dir=tmp_path / "groups")
    agent = OnboardingAgent(
        message_bus=bus,
        profile_store=profile_store,
        group_store=group_store,
    )
    await agent.initialize()
    await agent.start()
    return agent, profile_store, group_store, bus


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFirstTimeOnboarding:
    async def test_start_returns_greeting(self, tmp_path):
        agent, _, _, _ = await _make_onboarding_agent(tmp_path)
        greeting = await agent.start_onboarding("sess-001")
        assert "GENUS" in greeting or "Hallo" in greeting
        assert len(greeting) > 10

    async def test_full_onboarding_flow_creates_profile(self, tmp_path):
        agent, profile_store, _, bus = await _make_onboarding_agent(tmp_path)

        # Step 1: start
        await agent.start_onboarding("sess-002")

        # Step 2: give name
        response, done = await agent.process_onboarding_message("sess-002", "Max")
        assert done is False
        assert "Max" in response

        # Step 3: group type
        response, done = await agent.process_onboarding_message("sess-002", "Familie")
        assert done is False

        # Step 4: language
        response, done = await agent.process_onboarding_message("sess-002", "Deutsch")
        assert done is False

        # Step 5: response style → completes onboarding
        response, done = await agent.process_onboarding_message("sess-002", "kurz")
        assert done is True
        assert "Max" in response or "Willkommen" in response

    async def test_onboarding_complete_profile_saved(self, tmp_path):
        agent, profile_store, _, _ = await _make_onboarding_agent(tmp_path)

        await agent.start_onboarding("sess-003")
        await agent.process_onboarding_message("sess-003", "Lisa")
        await agent.process_onboarding_message("sess-003", "alleine")
        await agent.process_onboarding_message("sess-003", "en")
        _, done = await agent.process_onboarding_message("sess-003", "ausführlich")

        assert done is True
        all_profiles = await profile_store.list_all()
        user_ids = [p.user_id for p in all_profiles]
        assert any("lisa" in uid for uid in user_ids)

    async def test_onboarding_publishes_completed_topic(self, tmp_path):
        agent, _, _, bus = await _make_onboarding_agent(tmp_path)

        await agent.start_onboarding("sess-004")
        await agent.process_onboarding_message("sess-004", "Tim")
        await agent.process_onboarding_message("sess-004", "solo")
        await agent.process_onboarding_message("sess-004", "de")
        await agent.process_onboarding_message("sess-004", "kurz")

        topics = [call.args[0].topic for call in bus.publish.call_args_list]
        assert "identity.onboarding.completed" in topics

    async def test_onboarding_without_session_state_restarts(self, tmp_path):
        agent, _, _, _ = await _make_onboarding_agent(tmp_path)
        # Call process without start → agent creates session automatically
        response, done = await agent.process_onboarding_message("sess-new", "anything")
        assert done is False
        assert len(response) > 0


class TestKnownUserNewDevice:
    async def test_known_user_gets_device_greeting(self, tmp_path):
        from genus.identity.models import SystemRole, UserProfile

        agent, profile_store, _, _ = await _make_onboarding_agent(tmp_path)
        # Pre-create a profile
        p = UserProfile(
            user_id="known_user",
            display_name="Ronny",
            system_role=SystemRole.ADULT,
            onboarding_complete=True,
        )
        await profile_store.save(p)

        greeting = await agent.start_onboarding("sess-know", existing_token_user_id="known_user")
        assert "Ronny" in greeting
        assert "Gerät" in greeting or "Token" in greeting

    async def test_known_user_confirms_new_device(self, tmp_path):
        from genus.identity.models import SystemRole, UserProfile

        agent, profile_store, _, _ = await _make_onboarding_agent(tmp_path)
        p = UserProfile(
            user_id="known_user2",
            display_name="Alex",
            system_role=SystemRole.ADULT,
            onboarding_complete=True,
        )
        await profile_store.save(p)

        await agent.start_onboarding("sess-know2", existing_token_user_id="known_user2")
        response, done = await agent.process_onboarding_message("sess-know2", "ja")
        assert done is True
        assert "Alex" in response
