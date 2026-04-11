"""
Unit tests for NeedObserver persistence integration

Verifies:
- NeedObserver with NeedStore → state is loaded at startup
- After _handle_event() → NeedStore.save() is called
- After _dismiss_need() → NeedStore.dismiss() is called
- NeedObserver without NeedStore → pure in-memory (backward compatible)
"""

from unittest.mock import MagicMock, call

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.growth.identity_profile import StabilityRules
from genus.growth.need_observer import NeedObserver
from genus.growth.need_record import NeedRecord
from genus.growth.need_store import NeedStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bus() -> MessageBus:
    return MessageBus()


def _make_rules(min_trigger: int = 3) -> StabilityRules:
    """Return StabilityRules that require 3 triggers before any build."""
    return StabilityRules(min_trigger_count_before_build=min_trigger)


def _mock_store(existing_needs=None):
    """Return a MagicMock NeedStore whose load_all() returns *existing_needs*."""
    store = MagicMock()
    store.load_all.return_value = existing_needs or {}
    return store


# ---------------------------------------------------------------------------
# State loading at startup
# ---------------------------------------------------------------------------


class TestNeedObserverLoadsStateOnInit:
    def test_loads_state_from_store(self, tmp_path):
        """NeedObserver populates _needs from NeedStore.load_all() at init."""
        store = NeedStore(base_dir=tmp_path)
        record = NeedRecord(domain="system", need_description="run_failure", trigger_count=2)
        store.save(record)

        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=store)

        assert ("system", "run_failure") in observer._needs
        assert observer._needs[("system", "run_failure")].trigger_count == 2

    def test_load_all_called_once_on_init(self):
        """load_all() is called exactly once during NeedObserver.__init__."""
        mock_store = _mock_store()
        NeedObserver(message_bus=_make_bus(), need_store=mock_store)
        mock_store.load_all.assert_called_once()

    def test_empty_store_gives_empty_needs(self, tmp_path):
        """NeedObserver with an empty NeedStore starts with no needs."""
        store = NeedStore(base_dir=tmp_path)
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=store)

        assert observer._needs == {}

    def test_needs_restored_including_status(self, tmp_path):
        """NeedObserver restores the full NeedRecord including status field."""
        store = NeedStore(base_dir=tmp_path)
        record = NeedRecord(domain="quality", need_description="low_quality_score", trigger_count=3)
        record.status = "queued"
        store.save(record)

        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=store)

        restored = observer._needs[("quality", "low_quality_score")]
        assert restored.status == "queued"
        assert restored.trigger_count == 3


# ---------------------------------------------------------------------------
# save() called after state changes
# ---------------------------------------------------------------------------


class TestNeedObserverSavePersistence:
    async def test_save_called_after_handle_event(self):
        """NeedStore.save() is called after _handle_event records a need."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(
            message_bus=bus,
            stability_rules=_make_rules(min_trigger=3),
            need_store=mock_store,
        )
        await observer.initialize()

        await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

        mock_store.save.assert_called_once()
        saved_record = mock_store.save.call_args[0][0]
        assert saved_record.domain == "system"
        assert saved_record.need_description == "run_failure"

    async def test_save_called_multiple_times_for_multiple_events(self):
        """NeedStore.save() is called once per event regardless of trigger count."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(
            message_bus=bus,
            stability_rules=_make_rules(min_trigger=5),
            need_store=mock_store,
        )
        await observer.initialize()

        for _ in range(3):
            await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

        assert mock_store.save.call_count == 3

    async def test_save_called_after_status_becomes_queued(self):
        """NeedStore.save() is called with status='queued' when need reaches threshold."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(
            message_bus=bus,
            stability_rules=_make_rules(min_trigger=2),
            need_store=mock_store,
        )
        await observer.initialize()

        for _ in range(2):
            await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

        # Last save should have status="queued"
        last_saved = mock_store.save.call_args[0][0]
        assert last_saved.status == "queued"


# ---------------------------------------------------------------------------
# dismiss() called by _dismiss_need()
# ---------------------------------------------------------------------------


class TestNeedObserverDismissPersistence:
    def test_dismiss_called_when_dismiss_need_invoked(self):
        """NeedStore.dismiss() is called when _dismiss_need() is invoked."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=mock_store)
        observer._needs[("system", "run_failure")] = NeedRecord(
            domain="system", need_description="run_failure"
        )

        observer._dismiss_need("system", "run_failure")

        mock_store.dismiss.assert_called_once_with("system", "run_failure")

    def test_dismiss_removes_need_from_internal_state(self):
        """_dismiss_need() removes the need from _needs."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=mock_store)
        observer._needs[("system", "run_failure")] = NeedRecord(
            domain="system", need_description="run_failure"
        )

        observer._dismiss_need("system", "run_failure")

        assert ("system", "run_failure") not in observer._needs

    def test_dismiss_on_unknown_key_does_not_raise(self):
        """_dismiss_need() on a non-existent key does not raise."""
        mock_store = _mock_store()
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus, need_store=mock_store)

        # Should not raise even when the key doesn't exist.
        observer._dismiss_need("system", "nonexistent_need")

        mock_store.dismiss.assert_called_once_with("system", "nonexistent_need")


# ---------------------------------------------------------------------------
# Backward compatibility: no need_store → pure in-memory
# ---------------------------------------------------------------------------


class TestNeedObserverWithoutStore:
    async def test_in_memory_mode_when_no_store(self):
        """NeedObserver without need_store records needs in memory without errors."""
        bus = _make_bus()
        observer = NeedObserver(
            message_bus=bus,
            stability_rules=_make_rules(min_trigger=3),
        )
        await observer.initialize()

        await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

        assert ("system", "run_failure") in observer._needs

    async def test_no_store_no_persistence_calls(self):
        """No persistence methods are called when need_store is None."""
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus)
        await observer.initialize()

        # Should process event without AttributeError or side effects.
        await bus.publish(Message(topic="run.failed", payload={}, sender_id="test"))

        # _need_store is None; no error should have been raised.
        assert observer._need_store is None

    def test_stability_rules_defaults_when_omitted(self):
        """NeedObserver uses default StabilityRules when stability_rules is not provided."""
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus)

        # Default min_trigger_count_before_build is 2.
        assert observer._stability_rules.min_trigger_count_before_build == 2

    def test_dismiss_need_without_store_does_not_raise(self):
        """_dismiss_need() with need_store=None silently removes from _needs."""
        bus = _make_bus()
        observer = NeedObserver(message_bus=bus)
        observer._needs[("system", "run_failure")] = NeedRecord(
            domain="system", need_description="run_failure"
        )

        observer._dismiss_need("system", "run_failure")

        assert ("system", "run_failure") not in observer._needs
