"""
Tests for genus.memory.conversation_compressor — Phase 14b
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from genus.memory.conversation_compressor import compress_session
from genus.memory.episode_store import Episode


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


SAMPLE_MESSAGES = [
    _msg("user", "Ich möchte einen Python-Agenten bauen."),
    _msg("assistant", "Klar, womit soll ich anfangen?"),
    _msg("user", "Fang mit der Basisklasse an."),
    _msg("assistant", "Okay, hier ist die Basisklasse..."),
]


# ---------------------------------------------------------------------------
# Empty messages → immediate return
# ---------------------------------------------------------------------------

class TestEmptyMessages:
    async def test_empty_messages_returns_episode_with_zero_count(self):
        episode = await compress_session(
            session_id="sess-empty",
            user_id="alice",
            messages=[],
        )
        assert isinstance(episode, Episode)
        assert episode.message_count == 0
        assert episode.session_ids == ["sess-empty"]
        assert episode.user_id == "alice"

    async def test_empty_messages_source_is_fallback(self):
        episode = await compress_session(
            session_id="sess-x",
            user_id="bob",
            messages=[],
        )
        assert episode.source == "fallback"


# ---------------------------------------------------------------------------
# Without LLM → fallback
# ---------------------------------------------------------------------------

class TestFallbackPath:
    async def test_without_llm_source_is_fallback(self):
        episode = await compress_session(
            session_id="sess-1",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
        )
        assert episode.source == "fallback"

    async def test_without_llm_returns_episode(self):
        episode = await compress_session(
            session_id="sess-2",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
        )
        assert isinstance(episode, Episode)
        assert episode.message_count == len(SAMPLE_MESSAGES)

    async def test_without_llm_session_id_in_session_ids(self):
        episode = await compress_session(
            session_id="my-session-id",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
        )
        assert "my-session-id" in episode.session_ids


# ---------------------------------------------------------------------------
# With mock LLM → LLM path
# ---------------------------------------------------------------------------

class TestLLMPath:
    def _make_router(self, content: str) -> MagicMock:
        mock_response = MagicMock()
        mock_response.content = content

        router = MagicMock()
        router.complete = AsyncMock(return_value=mock_response)
        return router

    async def test_with_mock_llm_source_is_llm(self):
        router = self._make_router(
            json.dumps({
                "summary": "Wir haben über Python-Agenten gesprochen.",
                "topics": ["python", "agent"],
            })
        )
        episode = await compress_session(
            session_id="sess-llm",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert episode.source == "llm"

    async def test_with_mock_llm_summary_from_llm(self):
        expected_summary = "Wir haben über Python-Agenten gesprochen."
        router = self._make_router(
            json.dumps({"summary": expected_summary, "topics": ["python"]})
        )
        episode = await compress_session(
            session_id="sess-llm",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert episode.summary == expected_summary

    async def test_with_mock_llm_topics_from_llm(self):
        router = self._make_router(
            json.dumps({"summary": "Test", "topics": ["python", "agent", "basisklasse"]})
        )
        episode = await compress_session(
            session_id="sess-llm",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert "python" in episode.topics
        assert "agent" in episode.topics

    async def test_session_id_in_session_ids_with_llm(self):
        router = self._make_router(
            json.dumps({"summary": "Summary.", "topics": []})
        )
        episode = await compress_session(
            session_id="specific-session",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert "specific-session" in episode.session_ids


# ---------------------------------------------------------------------------
# Invalid JSON from LLM → fallback (no raise)
# ---------------------------------------------------------------------------

class TestLLMFallbackOnError:
    async def test_invalid_json_falls_back_to_fallback(self):
        mock_response = MagicMock()
        mock_response.content = "KEIN GÜLTIGES JSON {"

        router = MagicMock()
        router.complete = AsyncMock(return_value=mock_response)

        # Must not raise
        episode = await compress_session(
            session_id="sess-bad-json",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert isinstance(episode, Episode)
        assert episode.source == "fallback"

    async def test_llm_exception_falls_back(self):
        router = MagicMock()
        router.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        # Must not raise
        episode = await compress_session(
            session_id="sess-error",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert isinstance(episode, Episode)
        assert episode.source == "fallback"

    async def test_empty_summary_from_llm_falls_back(self):
        """LLM returns empty summary → fallback."""
        router = MagicMock()
        router.complete = AsyncMock(return_value=MagicMock(
            content=json.dumps({"summary": "", "topics": []})
        ))
        episode = await compress_session(
            session_id="sess-empty-summary",
            user_id="alice",
            messages=SAMPLE_MESSAGES,
            llm_router=router,
        )
        assert episode.source == "fallback"
