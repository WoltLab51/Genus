"""Unit tests for SituationContext and SituationStore — Phase 13c."""

from datetime import datetime, timedelta, timezone

import pytest

from genus.conversation.situation import (
    ActivityHint,
    LocationHint,
    SituationContext,
    SituationStore,
)


# ---------------------------------------------------------------------------
# SituationContext
# ---------------------------------------------------------------------------


class TestSituationContext:
    def test_defaults(self):
        ctx = SituationContext(user_id="user-1")
        assert ctx.location == LocationHint.UNKNOWN
        assert ctx.activity == ActivityHint.FREE
        assert ctx.next_appointment is None
        assert ctx.free_text is None
        assert ctx.ttl_minutes == 60

    def test_not_stale_when_fresh(self):
        ctx = SituationContext(user_id="user-1")
        assert not ctx.is_stale()

    def test_stale_after_ttl(self):
        old_time = datetime.now(timezone.utc) - timedelta(minutes=61)
        ctx = SituationContext(user_id="user-1", captured_at=old_time)
        assert ctx.is_stale()

    def test_not_stale_just_before_ttl(self):
        recent = datetime.now(timezone.utc) - timedelta(minutes=59)
        ctx = SituationContext(user_id="user-1", captured_at=recent)
        assert not ctx.is_stale()

    def test_custom_ttl(self):
        old_time = datetime.now(timezone.utc) - timedelta(minutes=16)
        ctx = SituationContext(user_id="user-1", captured_at=old_time, ttl_minutes=15)
        assert ctx.is_stale()

    def test_location_and_activity_fields(self):
        ctx = SituationContext(
            user_id="user-1",
            location=LocationHint.COMMUTING,
            activity=ActivityHint.APPOINTMENT_SOON,
            next_appointment="in 30 Minuten: Zahnarzt",
            free_text="fahre gerade zur Praxis",
        )
        assert ctx.location == LocationHint.COMMUTING
        assert ctx.activity == ActivityHint.APPOINTMENT_SOON
        assert ctx.next_appointment == "in 30 Minuten: Zahnarzt"
        assert ctx.free_text == "fahre gerade zur Praxis"

    def test_enum_values(self):
        assert LocationHint.HOME.value == "home"
        assert LocationHint.COMMUTING.value == "commuting"
        assert ActivityHint.IN_MEETING.value == "in_meeting"
        assert ActivityHint.BUSY.value == "busy"


# ---------------------------------------------------------------------------
# SituationStore
# ---------------------------------------------------------------------------


class TestSituationStore:
    def test_get_returns_none_for_unknown_user(self):
        store = SituationStore()
        assert store.get("unknown") is None

    def test_update_and_get(self):
        store = SituationStore()
        ctx = SituationContext(user_id="user-1", location=LocationHint.HOME)
        store.update(ctx)
        result = store.get("user-1")
        assert result is not None
        assert result.location == LocationHint.HOME

    def test_update_replaces_existing(self):
        store = SituationStore()
        ctx1 = SituationContext(user_id="user-1", location=LocationHint.HOME)
        ctx2 = SituationContext(user_id="user-1", location=LocationHint.WORK)
        store.update(ctx1)
        store.update(ctx2)
        assert store.get("user-1").location == LocationHint.WORK

    def test_get_returns_none_for_stale(self):
        store = SituationStore()
        old_time = datetime.now(timezone.utc) - timedelta(minutes=90)
        ctx = SituationContext(user_id="user-1", captured_at=old_time)
        store.update(ctx)
        assert store.get("user-1") is None

    def test_stale_evicted_from_store(self):
        store = SituationStore()
        old_time = datetime.now(timezone.utc) - timedelta(minutes=90)
        ctx = SituationContext(user_id="user-1", captured_at=old_time)
        store.update(ctx)
        store.get("user-1")  # triggers eviction
        # Internal store should no longer have the entry
        assert "user-1" not in store._store

    def test_clear(self):
        store = SituationStore()
        ctx = SituationContext(user_id="user-1")
        store.update(ctx)
        store.clear("user-1")
        assert store.get("user-1") is None

    def test_clear_noop_for_missing(self):
        store = SituationStore()
        # Should not raise
        store.clear("nobody")

    def test_independent_users(self):
        store = SituationStore()
        ctx1 = SituationContext(user_id="alice", location=LocationHint.HOME)
        ctx2 = SituationContext(user_id="bob", location=LocationHint.WORK)
        store.update(ctx1)
        store.update(ctx2)
        assert store.get("alice").location == LocationHint.HOME
        assert store.get("bob").location == LocationHint.WORK
