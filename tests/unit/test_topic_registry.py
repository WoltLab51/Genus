"""
Tests for genus.communication.topic_registry (TopicRegistry)

Verifies:
- register() + is_registered() + get()
- assert_registered() raises UnknownTopicError for unknown topics
- assert_registered(allow_unregistered=True) does not raise
- topics_for_domain() filters correctly
- owner_of() returns the correct owner
- Duplicate registration raises ValueError
- version field is present and >= 1
- DEFAULT_REGISTRY contains required well-known topics
"""

import pytest

from genus.communication.topic_registry import TopicEntry, TopicRegistry, UnknownTopicError
from genus.communication.topics import DEFAULT_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    topic: str,
    owner: str = "TestOwner",
    direction: str = "publish",
    domain: str = "quality",
    description: str = "Test topic",
    version: int = 1,
) -> TopicEntry:
    return TopicEntry(
        topic=topic,
        owner=owner,
        direction=direction,
        domain=domain,
        description=description,
        version=version,
    )


# ---------------------------------------------------------------------------
# TopicRegistry tests
# ---------------------------------------------------------------------------

class TestTopicRegistry:
    def test_register_and_is_registered(self):
        """register() must make is_registered() return True."""
        registry = TopicRegistry()
        registry.register(_entry("test.topic"))
        assert registry.is_registered("test.topic") is True

    def test_is_registered_false_for_unknown(self):
        """is_registered() must return False for unknown topics."""
        registry = TopicRegistry()
        assert registry.is_registered("unknown.topic") is False

    def test_get_returns_entry(self):
        """get() must return the registered TopicEntry."""
        registry = TopicRegistry()
        entry = _entry("test.topic", owner="AgentX")
        registry.register(entry)
        result = registry.get("test.topic")
        assert result is not None
        assert result.topic == "test.topic"
        assert result.owner == "AgentX"

    def test_get_returns_none_for_unknown(self):
        """get() must return None for unregistered topics."""
        registry = TopicRegistry()
        assert registry.get("does.not.exist") is None

    def test_assert_registered_raises_unknown_topic_error(self):
        """assert_registered() must raise UnknownTopicError for unknown topics."""
        registry = TopicRegistry()
        with pytest.raises(UnknownTopicError):
            registry.assert_registered("ghost.topic")

    def test_assert_registered_does_not_raise_for_known_topic(self):
        """assert_registered() must not raise for registered topics."""
        registry = TopicRegistry()
        registry.register(_entry("known.topic"))
        registry.assert_registered("known.topic")  # should not raise

    def test_assert_registered_allow_unregistered_true_does_not_raise(self):
        """assert_registered(allow_unregistered=True) must never raise."""
        registry = TopicRegistry()
        # No topics registered — still must not raise
        registry.assert_registered("debug.trace", allow_unregistered=True)

    def test_topics_for_domain_filters_correctly(self):
        """topics_for_domain() must return only entries matching the domain."""
        registry = TopicRegistry()
        registry.register(_entry("quality.scored", domain="quality"))
        registry.register(_entry("run.started", domain="run"))
        registry.register(_entry("run.failed", domain="run"))

        quality_topics = registry.topics_for_domain("quality")
        assert len(quality_topics) == 1
        assert quality_topics[0].topic == "quality.scored"

        run_topics = registry.topics_for_domain("run")
        assert len(run_topics) == 2

    def test_owner_of_returns_correct_owner(self):
        """owner_of() must return the owner string of a registered topic."""
        registry = TopicRegistry()
        registry.register(_entry("quality.scored", owner="QualityAgent"))
        assert registry.owner_of("quality.scored") == "QualityAgent"

    def test_owner_of_returns_none_for_unknown(self):
        """owner_of() must return None for unknown topics."""
        registry = TopicRegistry()
        assert registry.owner_of("ghost.topic") is None

    def test_duplicate_registration_raises_value_error(self):
        """Registering the same topic twice must raise ValueError."""
        registry = TopicRegistry()
        registry.register(_entry("test.topic"))
        with pytest.raises(ValueError):
            registry.register(_entry("test.topic"))

    def test_all_topics_returns_all_entries(self):
        """all_topics() must return every registered entry."""
        registry = TopicRegistry()
        for t in ("a.b", "c.d", "e.f"):
            registry.register(_entry(t))
        assert len(registry.all_topics()) == 3

    def test_version_present_and_gte_one(self):
        """Every registered TopicEntry must have version >= 1."""
        registry = TopicRegistry()
        registry.register(_entry("versioned.topic", version=2))
        entry = registry.get("versioned.topic")
        assert entry is not None
        assert entry.version >= 1

    def test_default_version_is_one(self):
        """Default version for TopicEntry must be 1."""
        entry = _entry("test.versioned")
        assert entry.version == 1


# ---------------------------------------------------------------------------
# DEFAULT_REGISTRY tests
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    """Verify the pre-populated DEFAULT_REGISTRY contains required topics."""

    REQUIRED_TOPICS = [
        "quality.scored",
        "outcome.recorded",
        "feedback.received",
        "run.started",
    ]

    def test_required_topics_registered(self):
        """DEFAULT_REGISTRY must contain all required well-known topics."""
        for topic in self.REQUIRED_TOPICS:
            assert DEFAULT_REGISTRY.is_registered(topic), (
                f"Expected topic {topic!r} to be in DEFAULT_REGISTRY"
            )

    def test_default_registry_has_multiple_domains(self):
        """DEFAULT_REGISTRY must span multiple domains."""
        domains = {e.domain for e in DEFAULT_REGISTRY.all_topics()}
        assert len(domains) >= 4

    def test_default_registry_run_topics(self):
        """DEFAULT_REGISTRY must include all run lifecycle topics."""
        required_run_topics = [
            "run.started",
            "run.completed",
            "run.failed",
            "run.step.started",
            "run.step.completed",
            "run.step.failed",
        ]
        for topic in required_run_topics:
            assert DEFAULT_REGISTRY.is_registered(topic), (
                f"run topic {topic!r} missing from DEFAULT_REGISTRY"
            )

    def test_default_registry_assert_registered_works(self):
        """assert_registered() on DEFAULT_REGISTRY must pass for known topics."""
        DEFAULT_REGISTRY.assert_registered("quality.scored")

    def test_default_registry_assert_registered_raises_for_unknown(self):
        """assert_registered() on DEFAULT_REGISTRY must raise for unknown topics."""
        with pytest.raises(UnknownTopicError):
            DEFAULT_REGISTRY.assert_registered("completely.unknown.topic.xyz")
