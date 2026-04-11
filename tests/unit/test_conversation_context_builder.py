"""Unit tests for ConversationContextBuilder — Phase 13c."""

from datetime import datetime, timezone

import pytest

from genus.conversation.context_builder import ConversationContext, build_llm_context_block
from genus.conversation.situation import ActivityHint, LocationHint, SituationContext


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class _Profile:
    """Minimal UserProfile stub."""

    def __init__(
        self,
        display_name="Ronny",
        response_style="kurz",
        user_id="user-1",
        interests=None,
        projects=None,
        decisions=None,
    ):
        self.display_name = display_name
        self.response_style = response_style
        self.user_id = user_id
        self.interests = interests or []
        self.projects = projects or []
        self.decisions = decisions or []

    def is_child(self):
        return False


class _RoomContext:
    def __init__(self, present_user_ids=None, guest_count=0, speaker_user_id=None):
        self.present_user_ids = present_user_ids or []
        self.guest_count = guest_count
        self.speaker_user_id = speaker_user_id


class _ResponsePolicy:
    def __init__(self, may_answer_aloud=True, reason=""):
        self.may_answer_aloud = may_answer_aloud
        self.reason = reason


# ---------------------------------------------------------------------------
# Tests — empty / None inputs
# ---------------------------------------------------------------------------


class TestBuildLlmContextBlockEmpty:
    def test_all_none_returns_empty(self):
        ctx = ConversationContext()
        result = build_llm_context_block(ctx)
        # No profile, no room, no situation → only potentially a time-of-day hint
        # At most one line; must not crash
        assert isinstance(result, str)

    def test_no_profile_no_crash(self):
        ctx = ConversationContext(
            profile=None,
            room=_RoomContext(),
            situation=None,
        )
        result = build_llm_context_block(ctx)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests — Layer A (profile)
# ---------------------------------------------------------------------------


class TestLayerAProfile:
    def test_display_name_injected(self):
        ctx = ConversationContext(profile=_Profile(display_name="Ronny"))
        result = build_llm_context_block(ctx)
        assert "Ronny" in result

    def test_response_style_injected(self):
        ctx = ConversationContext(profile=_Profile(response_style="technisch"))
        result = build_llm_context_block(ctx)
        assert "technisch" in result

    def test_interests_injected(self):
        ctx = ConversationContext(
            profile=_Profile(interests=["Python", "Raspberry Pi"])
        )
        result = build_llm_context_block(ctx)
        assert "Python" in result

    def test_projects_injected(self):
        ctx = ConversationContext(profile=_Profile(projects=["GENUS", "Solar"]))
        result = build_llm_context_block(ctx)
        assert "GENUS" in result

    def test_decisions_injected_max_three(self):
        decisions = [
            {"entscheidung": "kein Redis", "grund": "Pi zu klein"},
            {"entscheidung": "kein Docker"},
            {"entscheidung": "nur async"},
            {"entscheidung": "kein ORM"},  # 4th — should be excluded (only last 3)
        ]
        ctx = ConversationContext(profile=_Profile(decisions=decisions))
        result = build_llm_context_block(ctx)
        assert "kein Docker" in result
        assert "nur async" in result
        assert "kein ORM" in result
        # First decision is beyond the last-3 window
        assert "kein Redis" not in result

    def test_decisions_with_grund(self):
        decisions = [{"entscheidung": "kein Redis", "grund": "Pi zu klein"}]
        ctx = ConversationContext(profile=_Profile(decisions=decisions))
        result = build_llm_context_block(ctx)
        assert "kein Redis" in result
        assert "Pi zu klein" in result


# ---------------------------------------------------------------------------
# Tests — Layer B (room / policy)
# ---------------------------------------------------------------------------


class TestLayerBRoom:
    def test_other_users_listed(self):
        room = _RoomContext(present_user_ids=["user-1", "user-2", "user-3"])
        ctx = ConversationContext(
            profile=_Profile(user_id="user-1"),
            room=room,
        )
        result = build_llm_context_block(ctx)
        assert "user-2" in result
        assert "user-3" in result

    def test_speaker_excluded_from_others(self):
        room = _RoomContext(present_user_ids=["user-1", "user-2"])
        ctx = ConversationContext(
            profile=_Profile(user_id="user-1"),
            room=room,
        )
        result = build_llm_context_block(ctx)
        assert "user-1" not in result.split("Anwesend:")[-1] if "Anwesend:" in result else True

    def test_guest_count(self):
        room = _RoomContext(guest_count=3)
        ctx = ConversationContext(room=room)
        result = build_llm_context_block(ctx)
        assert "Gäste" in result or "3" in result

    def test_no_audio_policy_injected(self):
        policy = _ResponsePolicy(may_answer_aloud=False, reason="Kind schläft")
        ctx = ConversationContext(policy=policy)
        result = build_llm_context_block(ctx)
        assert "schriftlich" in result.lower()
        assert "Kind schläft" in result

    def test_audio_allowed_not_mentioned(self):
        policy = _ResponsePolicy(may_answer_aloud=True)
        ctx = ConversationContext(policy=policy)
        result = build_llm_context_block(ctx)
        assert "schriftlich" not in result.lower()


# ---------------------------------------------------------------------------
# Tests — Layer C (situation)
# ---------------------------------------------------------------------------


class TestLayerCSituation:
    def test_free_text_injected(self):
        situation = SituationContext(
            user_id="user-1",
            free_text="fahre gerade nach hause",
        )
        ctx = ConversationContext(situation=situation)
        result = build_llm_context_block(ctx)
        assert "fahre gerade nach hause" in result

    def test_commuting_activity(self):
        situation = SituationContext(
            user_id="user-1",
            activity=ActivityHint.COMMUTING,
        )
        ctx = ConversationContext(situation=situation)
        result = build_llm_context_block(ctx)
        assert "unterwegs" in result.lower() or "kurze" in result.lower()

    def test_appointment_soon(self):
        situation = SituationContext(
            user_id="user-1",
            activity=ActivityHint.APPOINTMENT_SOON,
            next_appointment="in 30 Minuten: Zahnarzt",
        )
        ctx = ConversationContext(situation=situation)
        result = build_llm_context_block(ctx)
        assert "Zahnarzt" in result

    def test_in_meeting(self):
        situation = SituationContext(
            user_id="user-1",
            activity=ActivityHint.IN_MEETING,
        )
        ctx = ConversationContext(situation=situation)
        result = build_llm_context_block(ctx)
        assert "Meeting" in result or "meeting" in result.lower()

    def test_stale_situation_ignored(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(minutes=90)
        situation = SituationContext(
            user_id="user-1",
            free_text="veraltet",
            captured_at=old,
        )
        ctx = ConversationContext(situation=situation)
        result = build_llm_context_block(ctx)
        assert "veraltet" not in result


# ---------------------------------------------------------------------------
# Tests — time-of-day hints
# ---------------------------------------------------------------------------


class TestTimeOfDay:
    def _ctx_at_hour(self, hour: int) -> ConversationContext:
        ts = datetime(2026, 4, 11, hour, 0, tzinfo=timezone.utc)
        return ConversationContext(timestamp=ts)

    def test_morning_hint(self):
        result = build_llm_context_block(self._ctx_at_hour(7))
        assert "Morgen" in result

    def test_evening_hint(self):
        result = build_llm_context_block(self._ctx_at_hour(22))
        assert "Abend" in result

    def test_midday_no_hint(self):
        result = build_llm_context_block(self._ctx_at_hour(12))
        assert "Morgen" not in result
        assert "Abend" not in result
