"""Unit tests for ParentalAgent — Phase 14."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from genus.agents.parental_agent import ParentalAgent
from genus.communication.message_bus import MessageBus
from genus.identity.models import ChildSettings, SystemRole, UserProfile
from genus.identity.profile_store import ProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_bus() -> MagicMock:
    bus = MagicMock(spec=MessageBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
async def profile_store(tmp_path) -> ProfileStore:
    store = ProfileStore(base_dir=tmp_path / "profiles")
    child = UserProfile(
        user_id="kind_a",
        display_name="Kind A",
        system_role=SystemRole.CHILD,
        child_settings=ChildSettings(
            max_screen_time_minutes=60,
            bedtime_hour=23,
            allowed_agents=["conversation", "dnd_master"],
            report_to=["ronny_wolter"],
        ),
    )
    await store.save(child)
    return store


@pytest.fixture
def bus():
    return _make_bus()


@pytest.fixture
async def agent(bus, profile_store) -> ParentalAgent:
    a = ParentalAgent(message_bus=bus, profile_store=profile_store)
    await a.initialize()
    await a.start()
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScreenTimeLimitNotReached:
    async def test_fresh_child_has_access(self, agent):
        has_access, msg = await agent.check_and_enforce_limits("kind_a")
        assert has_access is True
        assert msg == ""

    async def test_partial_usage_still_has_access(self, agent):
        await agent.track_usage("kind_a", 30.0)
        has_access, _ = await agent.check_and_enforce_limits("kind_a")
        assert has_access is True


class TestScreenTimeLimitReached:
    async def test_limit_exceeded_blocks_access(self, agent, bus):
        await agent.track_usage("kind_a", 60.0)
        has_access, msg = await agent.check_and_enforce_limits("kind_a")
        assert has_access is False
        assert "heute" in msg or "Stunde" in msg or "Minute" in msg

    async def test_limit_reached_publishes_event(self, agent, bus):
        await agent.track_usage("kind_a", 60.0)
        await agent.check_and_enforce_limits("kind_a")
        bus.publish.assert_called()
        topics = [call.args[0].topic for call in bus.publish.call_args_list]
        assert "parental.screen_time.limit_reached" in topics


class TestCriticalQuestionFlag:
    async def test_flag_publishes_event(self, agent, bus):
        await agent.flag_critical_question("kind_a", "Was ist Alkohol?", "nsfw")
        bus.publish.assert_called_once()
        msg = bus.publish.call_args[0][0]
        assert msg.topic == "parental.flag.critical_question"
        assert msg.payload["topic"] == "nsfw"
        assert "kind_a" == msg.payload["child_user_id"]
        assert "ronny_wolter" in msg.payload["report_to"]


class TestDailyReport:
    async def test_report_contains_required_fields(self, agent):
        await agent.track_usage("kind_a", 47.0)
        report = await agent.generate_daily_report("kind_a")
        assert "child" in report
        assert "date" in report
        assert "screen_time_minutes" in report
        assert report["screen_time_minutes"] == 47.0

    async def test_report_publishes_daily_report_topic(self, agent, bus):
        await agent.generate_daily_report("kind_a")
        topics = [call.args[0].topic for call in bus.publish.call_args_list]
        assert "parental.report.daily" in topics


class TestAdultNotAffected:
    async def test_adult_always_has_access(self, agent, tmp_path, bus):
        # Save an adult user
        from genus.identity.profile_store import ProfileStore
        store = ProfileStore(base_dir=tmp_path / "profiles")
        adult = UserProfile(user_id="adult_x", display_name="Adult X", system_role=SystemRole.ADULT)
        await store.save(adult)
        adult_agent = ParentalAgent(message_bus=bus, profile_store=store)
        await adult_agent.initialize()
        await adult_agent.start()
        await adult_agent.track_usage("adult_x", 999.0)
        has_access, _ = await adult_agent.check_and_enforce_limits("adult_x")
        assert has_access is True
