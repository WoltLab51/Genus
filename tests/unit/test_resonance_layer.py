"""Unit tests for genus.memory.resonance_layer — Phase 15a."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from genus.memory.resonance_layer import build_resonance_block, _RESONANCE_HEADER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_episode(
    summary: str = "Test summary",
    topics: list[str] | None = None,
    created_at: str = "2024-04-01T12:00:00+00:00",
    user_id: str = "user1",
) -> MagicMock:
    ep = MagicMock()
    ep.summary = summary
    ep.topics = topics or []
    ep.created_at = created_at
    ep.user_id = user_id
    return ep


def make_fact(key: str, value: str) -> MagicMock:
    f = MagicMock()
    f.key = key
    f.value = value
    return f


def make_episode_store(episodes: list | None = None) -> MagicMock:
    store = MagicMock()
    store.get_recent.return_value = episodes or []
    return store


def make_fact_store(facts: dict | None = None) -> MagicMock:
    store = MagicMock()
    store.get_all.return_value = facts or {}
    return store


def make_inner_monologue(note: str | None = None) -> MagicMock:
    im = MagicMock()
    im.get_current.return_value = note
    return im


# ---------------------------------------------------------------------------
# Tests — all None stores
# ---------------------------------------------------------------------------


class TestBuildResonanceBlockNoStores:
    def test_all_none_returns_empty_string(self):
        result = build_resonance_block("user1")
        assert result == ""

    def test_episode_store_none_returns_empty(self):
        result = build_resonance_block(
            "user1",
            fact_store=None,
            inner_monologue=None,
        )
        assert result == ""


# ---------------------------------------------------------------------------
# Tests — empty stores
# ---------------------------------------------------------------------------


class TestBuildResonanceBlockEmptyStores:
    def test_empty_episode_store_no_episode_block(self):
        store = make_episode_store([])
        result = build_resonance_block("user1", episode_store=store)
        assert result == ""
        assert "Erinnerungen" not in result

    def test_empty_fact_store_no_fact_block(self):
        store = make_fact_store({})
        result = build_resonance_block("user1", fact_store=store)
        assert result == ""

    def test_inner_monologue_none_note_no_block(self):
        im = make_inner_monologue(None)
        result = build_resonance_block("user1", inner_monologue=im)
        assert result == ""


# ---------------------------------------------------------------------------
# Tests — with data
# ---------------------------------------------------------------------------


class TestBuildResonanceBlockWithEpisodes:
    def test_episodes_block_contains_date_and_summary(self):
        ep = make_episode(
            summary="Wir haben über Solar gesprochen",
            topics=["solar"],
            created_at="2024-04-05T10:00:00+00:00",
        )
        store = make_episode_store([ep])
        result = build_resonance_block("user1", episode_store=store)
        assert _RESONANCE_HEADER in result
        assert "Erinnerungen" in result
        assert "05.04.2024" in result
        assert "Solar" in result or "solar" in result

    def test_episodes_block_contains_topics(self):
        ep = make_episode(
            summary="Gespräch über Energie",
            topics=["solar", "energie"],
            created_at="2024-04-05T10:00:00+00:00",
        )
        store = make_episode_store([ep])
        result = build_resonance_block("user1", episode_store=store)
        assert "solar" in result or "energie" in result

    def test_multiple_episodes_both_present(self):
        ep1 = make_episode(
            summary="Älteres Gespräch",
            created_at="2024-04-01T10:00:00+00:00",
        )
        ep2 = make_episode(
            summary="Neueres Gespräch",
            created_at="2024-04-05T10:00:00+00:00",
        )
        store = make_episode_store([ep1, ep2])
        result = build_resonance_block("user1", episode_store=store)
        assert "Älteres" in result
        assert "Neueres" in result

    def test_max_episodes_respected(self):
        episodes = [
            make_episode(summary=f"Episode {i}", created_at=f"2024-04-0{i+1}T10:00:00+00:00")
            for i in range(5)
        ]
        store = MagicMock()
        store.get_recent.return_value = episodes[:2]  # simulates limit=2
        result = build_resonance_block("user1", episode_store=store, max_episodes=2)
        store.get_recent.assert_called_once_with("user1", limit=2)


class TestBuildResonanceBlockEpisodeTruncation:
    def test_long_summary_truncated_at_300_chars(self):
        long_summary = "X" * 400
        ep = make_episode(summary=long_summary, created_at="2024-04-01T10:00:00+00:00")
        store = make_episode_store([ep])
        result = build_resonance_block("user1", episode_store=store)
        # Summary should be truncated to 300 chars + "..."
        assert "..." in result
        # The "XXX..." block should not exceed 300 + 3 chars
        lines = result.split("\n")
        summary_line = [l for l in lines if "X" in l][0]
        content = summary_line.split(": ", 1)[1] if ": " in summary_line else summary_line
        assert len(content) <= 303  # 300 chars + "..."

    def test_short_summary_not_truncated(self):
        ep = make_episode(
            summary="Kurze Zusammenfassung",
            created_at="2024-04-01T10:00:00+00:00",
        )
        store = make_episode_store([ep])
        result = build_resonance_block("user1", episode_store=store)
        assert "..." not in result
        assert "Kurze Zusammenfassung" in result


class TestBuildResonanceBlockWithFacts:
    def test_facts_block_contains_key_value(self):
        f = make_fact("preference.response_style", "kurz")
        store = make_fact_store({"preference.response_style": f})
        result = build_resonance_block("user1", fact_store=store)
        assert _RESONANCE_HEADER in result
        assert "Bekannte Fakten" in result
        assert "preference.response_style" in result
        assert "kurz" in result

    def test_facts_with_empty_value_excluded(self):
        f_empty = make_fact("empty_key", "")
        f_valid = make_fact("valid_key", "valid_value")
        store = make_fact_store({"empty_key": f_empty, "valid_key": f_valid})
        result = build_resonance_block("user1", fact_store=store)
        assert "empty_key" not in result
        assert "valid_key" in result


class TestBuildResonanceBlockWithInnerMonologue:
    def test_inner_note_included_in_block(self):
        im = make_inner_monologue("Emma wirkte heute gestresst.")
        result = build_resonance_block("user1", inner_monologue=im)
        assert _RESONANCE_HEADER in result
        assert "Innere Notiz" in result
        assert "Emma wirkte heute gestresst." in result

    def test_none_inner_note_excluded(self):
        im = make_inner_monologue(None)
        result = build_resonance_block("user1", inner_monologue=im)
        assert result == ""


class TestBuildResonanceBlockAllTogether:
    def test_all_three_sources_produces_full_block(self):
        ep = make_episode(
            summary="Solar-Gespräch",
            topics=["solar"],
            created_at="2024-04-05T10:00:00+00:00",
        )
        ep_store = make_episode_store([ep])
        f = make_fact("name", "Ronny")
        f_store = make_fact_store({"name": f})
        im = make_inner_monologue("Positives Gespräch.")

        result = build_resonance_block(
            "user1",
            episode_store=ep_store,
            fact_store=f_store,
            inner_monologue=im,
        )
        assert _RESONANCE_HEADER in result
        assert "Erinnerungen" in result
        assert "Bekannte Fakten" in result
        assert "Innere Notiz" in result
        assert "Ronny" in result
        assert "Positives Gespräch." in result


# ---------------------------------------------------------------------------
# Tests — graceful degradation
# ---------------------------------------------------------------------------


class TestBuildResonanceBlockGracefulDegradation:
    def test_episode_store_raises_no_crash(self):
        store = MagicMock()
        store.get_recent.side_effect = RuntimeError("disk error")
        # Should not raise; graceful degradation
        result = build_resonance_block("user1", episode_store=store)
        assert isinstance(result, str)

    def test_fact_store_raises_no_crash(self):
        store = MagicMock()
        store.get_all.side_effect = RuntimeError("db error")
        result = build_resonance_block("user1", fact_store=store)
        assert isinstance(result, str)

    def test_inner_monologue_raises_no_crash(self):
        im = MagicMock()
        im.get_current.side_effect = RuntimeError("io error")
        result = build_resonance_block("user1", inner_monologue=im)
        assert isinstance(result, str)

    def test_all_raise_returns_empty_string(self):
        ep_store = MagicMock()
        ep_store.get_recent.side_effect = RuntimeError("disk")
        f_store = MagicMock()
        f_store.get_all.side_effect = RuntimeError("db")
        im = MagicMock()
        im.get_current.side_effect = RuntimeError("io")
        result = build_resonance_block(
            "user1",
            episode_store=ep_store,
            fact_store=f_store,
            inner_monologue=im,
        )
        assert result == ""
