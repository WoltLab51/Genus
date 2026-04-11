"""
Integration tests for NeedObserver state persistence across restarts.

Verifies that NeedObserver state (recorded needs) survives a simulated
process restart by persisting through a shared NeedStore.
"""

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.growth.need_observer import NeedObserver
from genus.growth.need_store import NeedStore


async def test_need_observer_survives_restart(tmp_path):
    """NeedObserver state persists across a simulated restart.

    A first observer records quality needs by processing quality.scored events.
    After stopping the first observer a second observer is created with the
    same NeedStore and must have the previously recorded state.
    """
    need_store = NeedStore(base_dir=tmp_path)
    bus = MessageBus()

    # ------------------------------------------------------------------ #
    # First observer: build up state                                      #
    # ------------------------------------------------------------------ #
    observer1 = NeedObserver(message_bus=bus, need_store=need_store)
    await observer1.initialize()
    await observer1.start()

    # Publish three low-quality score events (threshold is 2 by default).
    for _ in range(3):
        await bus.publish(
            Message(
                topic="quality.scored",
                payload={"quality_score": 0.3, "run_id": "r1"},
                sender_id="test",
            )
        )

    await observer1.stop()

    # ------------------------------------------------------------------ #
    # Second observer: load persisted state                               #
    # ------------------------------------------------------------------ #
    observer2 = NeedObserver(message_bus=bus, need_store=need_store)
    await observer2.initialize()

    needs = observer2._needs
    assert len(needs) > 0, "No needs were restored — state was not persisted"
    assert any(
        "low_quality" in key[1] for key in needs.keys()
    ), f"Expected a 'low_quality*' need, got: {list(needs.keys())}"


async def test_need_observer_restart_preserves_trigger_count(tmp_path):
    """Restored NeedRecords have the correct trigger_count from before the restart."""
    need_store = NeedStore(base_dir=tmp_path)
    bus = MessageBus()

    observer1 = NeedObserver(message_bus=bus, need_store=need_store)
    await observer1.initialize()
    await observer1.start()

    for _ in range(3):
        await bus.publish(
            Message(
                topic="quality.scored",
                payload={"quality_score": 0.3},
                sender_id="test",
            )
        )

    await observer1.stop()

    # Create a NEW NeedStore instance to simulate a full process restart.
    new_store = NeedStore(base_dir=tmp_path)
    observer2 = NeedObserver(message_bus=bus, need_store=new_store)
    await observer2.initialize()

    key = ("quality", "low_quality_score")
    assert key in observer2._needs
    assert observer2._needs[key].trigger_count == 3


async def test_need_observer_multiple_needs_survive_restart(tmp_path):
    """Multiple distinct needs are all restored after a restart."""
    need_store = NeedStore(base_dir=tmp_path)
    bus = MessageBus()

    observer1 = NeedObserver(message_bus=bus, need_store=need_store)
    await observer1.initialize()
    await observer1.start()

    # Trigger run_failure needs.
    await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

    # Trigger quality needs.
    await bus.publish(
        Message(topic="quality.scored", payload={"quality_score": 0.3}, sender_id="test")
    )

    await observer1.stop()

    new_store = NeedStore(base_dir=tmp_path)
    observer2 = NeedObserver(message_bus=bus, need_store=new_store)
    await observer2.initialize()

    assert ("system", "run_failure") in observer2._needs
    assert ("quality", "low_quality_score") in observer2._needs
