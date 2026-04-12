"""Unit tests for PromptStrategy / resolve_prompt_strategy — Phase 13c."""

import pytest

from genus.conversation.prompt_strategy import PromptStrategy, resolve_prompt_strategy
from genus.conversation.situation import ActivityHint, SituationContext
from genus.llm.router import TaskType


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _Profile:
    def __init__(self, response_style="kurz", is_child_flag=False):
        self.response_style = response_style
        self._is_child = is_child_flag

    def is_child(self):
        return self._is_child


class _Policy:
    def __init__(self, may_answer_aloud=True):
        self.may_answer_aloud = may_answer_aloud


# ---------------------------------------------------------------------------
# Tests — base strategies per intent
# ---------------------------------------------------------------------------


class TestBaseStrategies:
    def test_chat_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.CHAT)
        assert s.task_type == TaskType.GENERAL
        assert s.max_tokens == 200
        assert s.temperature == 0.7

    def test_question_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.QUESTION)
        assert s.task_type == TaskType.REASONING
        assert s.max_tokens == 500
        assert s.temperature == 0.2

    def test_memory_request_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.MEMORY_REQUEST)
        assert s.task_type == TaskType.SUMMARIZE
        assert s.include_episodic is True

    def test_dev_request_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.DEV_REQUEST)
        assert s.task_type == TaskType.PLANNING
        assert s.max_tokens == 800

    def test_status_request_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.STATUS_REQUEST)
        assert s.include_profile is False
        assert s.include_episodic is True

    def test_unknown_intent_fallback(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.UNKNOWN)
        assert isinstance(s, PromptStrategy)
        assert s.max_tokens > 0

    def test_situation_update_intent(self):
        from genus.conversation.conversation_agent import Intent
        s = resolve_prompt_strategy(Intent.SITUATION_UPDATE)
        assert s.task_type == TaskType.GENERAL
        assert s.max_tokens <= 200


# ---------------------------------------------------------------------------
# Tests — response_style adjustments
# ---------------------------------------------------------------------------


class TestResponseStyleAdjustments:
    def _intent(self):
        from genus.conversation.conversation_agent import Intent
        return Intent.CHAT  # base: 200 tokens

    def test_kurz_halves_tokens(self):
        profile = _Profile(response_style="kurz")
        s = resolve_prompt_strategy(self._intent(), profile=profile)
        assert s.max_tokens == 100  # 200 * 0.5

    def test_ausfuehrlich_doubles_tokens(self):
        profile = _Profile(response_style="ausführlich")
        s = resolve_prompt_strategy(self._intent(), profile=profile)
        assert s.max_tokens == 400  # 200 * 2.0

    def test_technisch_increases_and_lowers_temp(self):
        profile = _Profile(response_style="technisch")
        s = resolve_prompt_strategy(self._intent(), profile=profile)
        assert s.max_tokens == 300  # 200 * 1.5
        assert s.temperature == 0.1

    def test_unknown_style_no_change(self):
        profile = _Profile(response_style="unbekannt")
        s = resolve_prompt_strategy(self._intent(), profile=profile)
        assert s.max_tokens == 200  # unchanged


# ---------------------------------------------------------------------------
# Tests — child user cap
# ---------------------------------------------------------------------------


class TestChildUserCap:
    def test_child_hard_cap(self):
        from genus.conversation.conversation_agent import Intent
        profile = _Profile(response_style="ausführlich", is_child_flag=True)
        s = resolve_prompt_strategy(Intent.DEV_REQUEST, profile=profile)
        assert s.max_tokens <= 200  # cap enforced

    def test_child_temperature_raised(self):
        from genus.conversation.conversation_agent import Intent
        profile = _Profile(is_child_flag=True)
        s = resolve_prompt_strategy(Intent.CHAT, profile=profile)
        assert s.temperature == 0.5


# ---------------------------------------------------------------------------
# Tests — COMMUTING halves tokens
# ---------------------------------------------------------------------------


class TestCommutingHalvesTokens:
    def test_commuting_halves_tokens(self):
        from genus.conversation.conversation_agent import Intent
        situation = SituationContext(
            user_id="u1",
            activity=ActivityHint.COMMUTING,
        )
        # Base for QUESTION = 500 tokens, kurz → 250, then commuting halves → 125
        profile = _Profile(response_style="ausführlich")
        s = resolve_prompt_strategy(Intent.QUESTION, profile=profile, situation=situation)
        # Without commuting: 500 * 2.0 = 1000; with commuting: 500
        assert s.max_tokens == 500

    def test_no_commuting_no_change(self):
        from genus.conversation.conversation_agent import Intent
        situation = SituationContext(
            user_id="u1",
            activity=ActivityHint.FREE,
        )
        s = resolve_prompt_strategy(Intent.QUESTION, situation=situation)
        assert s.max_tokens == 500

    def test_stale_situation_no_commuting_effect(self):
        from datetime import timedelta, timezone
        from datetime import datetime
        from genus.conversation.conversation_agent import Intent
        old = datetime.now(timezone.utc) - timedelta(minutes=90)
        situation = SituationContext(
            user_id="u1",
            activity=ActivityHint.COMMUTING,
            captured_at=old,
        )
        s = resolve_prompt_strategy(Intent.QUESTION, situation=situation)
        # Stale → commuting rule not applied
        assert s.max_tokens == 500


# ---------------------------------------------------------------------------
# Tests — ResponsePolicy
# ---------------------------------------------------------------------------


class TestResponsePolicy:
    def test_no_audio_strips_profile(self):
        from genus.conversation.conversation_agent import Intent
        policy = _Policy(may_answer_aloud=False)
        s = resolve_prompt_strategy(Intent.CHAT, response_policy=policy)
        assert s.include_profile is False

    def test_audio_allowed_keeps_profile(self):
        from genus.conversation.conversation_agent import Intent
        policy = _Policy(may_answer_aloud=True)
        s = resolve_prompt_strategy(Intent.CHAT, response_policy=policy)
        assert s.include_profile is True
