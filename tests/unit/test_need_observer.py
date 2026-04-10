"""
Tests for genus.growth.need_observer (NeedObserver)

Verifies:
- After 1 trigger: no need.identified published (trigger_count < min)
- After 2 triggers: need.identified is published
- After publishing: status = "queued", no second need.identified
- feedback.received with outcome="failure" → Need in domain "system"
- run.failed → Need in domain "system"
- quality.scored with quality_score=0.40 → Need in domain "quality"
- quality.scored with quality_score=0.80 → no Need
- Different (domain, need_description) pairs → separate NeedRecords
"""

from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.growth.identity_profile import StabilityRules
from genus.growth.need_observer import NeedObserver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bus() -> MessageBus:
    return MessageBus()


def _make_rules(min_trigger: int = 2) -> StabilityRules:
    return StabilityRules(min_trigger_count_before_build=min_trigger)


def _collect_published(bus: MessageBus, topic: str) -> List[Message]:
    """Subscribe to *topic* and collect all messages published on it."""
    collected: List[Message] = []

    def _handler(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, "__test_collector__", _handler)
    return collected


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNeedObserverFeedbackReceived:
    async def test_no_publish_after_one_trigger(self):
        """One feedback.received failure event does not trigger need.identified."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        await bus.publish(Message(
            topic="feedback.received",
            payload={"outcome": "failure"},
            sender_id="test",
        ))
        assert len(published) == 0

    async def test_publish_after_two_triggers(self):
        """Two feedback.received failure events trigger need.identified."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        for _ in range(2):
            await bus.publish(Message(
                topic="feedback.received",
                payload={"outcome": "failure"},
                sender_id="test",
            ))
        assert len(published) == 1

    async def test_no_second_publish_after_status_queued(self):
        """After need.identified is published once, further triggers produce no more events."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        for _ in range(5):
            await bus.publish(Message(
                topic="feedback.received",
                payload={"outcome": "failure"},
                sender_id="test",
            ))
        assert len(published) == 1

    async def test_status_queued_after_publish(self):
        """The NeedRecord status is set to 'queued' after need.identified is published."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        await observer.initialize()
        for _ in range(2):
            await bus.publish(Message(
                topic="feedback.received",
                payload={"outcome": "failure"},
                sender_id="test",
            ))
        key = ("system", "repeated_failure")
        assert observer._needs[key].status == "queued"

    async def test_non_failure_outcome_ignored(self):
        """feedback.received with outcome != 'failure' does not create a need."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=1)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        await bus.publish(Message(
            topic="feedback.received",
            payload={"outcome": "success"},
            sender_id="test",
        ))
        assert len(published) == 0


class TestNeedObserverRunFailed:
    async def test_run_failed_creates_system_need(self):
        """run.failed event creates a need in domain 'system' with 'run_failure'."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        await observer.initialize()
        await bus.publish(Message(
            topic="run.failed",
            payload={"error": "timeout"},
            sender_id="test",
        ))
        key = ("system", "run_failure")
        assert key in observer._needs
        assert observer._needs[key].trigger_count == 1

    async def test_run_failed_two_triggers_publishes(self):
        """Two run.failed events trigger need.identified."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        for _ in range(2):
            await bus.publish(Message(
                topic="run.failed",
                payload={},
                sender_id="test",
            ))
        assert len(published) == 1
        assert published[0].payload["domain"] == "system"


class TestNeedObserverQualityScored:
    async def test_low_quality_score_creates_need(self):
        """quality.scored with quality_score=0.40 creates a quality need."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        await observer.initialize()
        await bus.publish(Message(
            topic="quality.scored",
            payload={"quality_score": 0.40},
            sender_id="test",
        ))
        key = ("quality", "low_quality_score")
        assert key in observer._needs

    async def test_high_quality_score_ignored(self):
        """quality.scored with quality_score=0.80 does not create a need."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=1)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        await bus.publish(Message(
            topic="quality.scored",
            payload={"quality_score": 0.80},
            sender_id="test",
        ))
        assert len(published) == 0

    async def test_boundary_quality_score_ignored(self):
        """quality.scored with quality_score=0.55 (boundary, not < 0.55) → no need."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=1)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        await bus.publish(Message(
            topic="quality.scored",
            payload={"quality_score": 0.55},
            sender_id="test",
        ))
        assert len(published) == 0

    async def test_quality_need_published_after_two_triggers(self):
        """Two low-quality scores trigger need.identified in domain 'quality'."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        for _ in range(2):
            await bus.publish(Message(
                topic="quality.scored",
                payload={"quality_score": 0.40},
                sender_id="test",
            ))
        assert len(published) == 1
        assert published[0].payload["domain"] == "quality"


class TestNeedObserverSeparateRecords:
    async def test_different_pairs_are_separate_records(self):
        """Different (domain, need_description) pairs produce independent NeedRecords."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        await observer.initialize()
        # trigger system/repeated_failure once
        await bus.publish(Message(
            topic="feedback.received",
            payload={"outcome": "failure"},
            sender_id="test",
        ))
        # trigger system/run_failure once
        await bus.publish(Message(
            topic="run.failed",
            payload={},
            sender_id="test",
        ))
        assert ("system", "repeated_failure") in observer._needs
        assert ("system", "run_failure") in observer._needs
        assert observer._needs[("system", "repeated_failure")].trigger_count == 1
        assert observer._needs[("system", "run_failure")].trigger_count == 1

    async def test_separate_records_published_independently(self):
        """Two separate needs each trigger their own need.identified event."""
        bus = _make_bus()
        rules = _make_rules(min_trigger=2)
        observer = NeedObserver(message_bus=bus, stability_rules=rules)
        published: List[Message] = _collect_published(bus, "need.identified")
        await observer.initialize()
        for _ in range(2):
            await bus.publish(Message(
                topic="feedback.received",
                payload={"outcome": "failure"},
                sender_id="test",
            ))
        for _ in range(2):
            await bus.publish(Message(
                topic="run.failed",
                payload={},
                sender_id="test",
            ))
        assert len(published) == 2
        domains = {m.payload["domain"] for m in published}
        descs = {m.payload["need_description"] for m in published}
        assert "system" in domains
        assert "repeated_failure" in descs
        assert "run_failure" in descs
