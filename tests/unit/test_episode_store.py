"""
Tests for genus.memory.episode_store — Phase 14b
"""

import json
import pytest
from pathlib import Path

from genus.memory.episode_store import Episode, EpisodeStore


# ---------------------------------------------------------------------------
# Episode round-trip
# ---------------------------------------------------------------------------

class TestEpisodeRoundTrip:
    def test_to_dict_from_dict_roundtrip(self):
        ep = Episode.create(
            user_id="alice",
            summary="Wir haben über Python gesprochen.",
            topics=["python", "programmierung"],
            session_ids=["sess-1", "sess-2"],
            message_count=10,
            source="llm",
        )
        restored = Episode.from_dict(ep.to_dict())
        assert restored.episode_id == ep.episode_id
        assert restored.user_id == ep.user_id
        assert restored.summary == ep.summary
        assert restored.topics == ep.topics
        assert restored.session_ids == ep.session_ids
        assert restored.created_at == ep.created_at
        assert restored.message_count == ep.message_count
        assert restored.source == ep.source

    def test_from_dict_defaults(self):
        """from_dict must handle optional / missing fields gracefully."""
        data = {
            "episode_id": "abc-123",
            "user_id": "bob",
            "summary": "Kurze Zusammenfassung.",
            "created_at": "2026-04-01T00:00:00+00:00",
        }
        ep = Episode.from_dict(data)
        assert ep.topics == []
        assert ep.session_ids == []
        assert ep.message_count == 0
        assert ep.source == "fallback"


# ---------------------------------------------------------------------------
# EpisodeStore.append()
# ---------------------------------------------------------------------------

class TestEpisodeStoreAppend:
    def test_append_writes_jsonl(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        ep = Episode.create(
            user_id="alice",
            summary="Test summary",
            topics=["test"],
            session_ids=["s1"],
            message_count=3,
            source="fallback",
        )
        store.append(ep)

        # Verify the file was created and contains valid JSON
        jsonl_file = store._file_path("alice")
        assert jsonl_file.exists()
        lines = jsonl_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["episode_id"] == ep.episode_id
        assert data["summary"] == "Test summary"

    def test_append_multiple_episodes(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        for i in range(3):
            ep = Episode.create(
                user_id="bob",
                summary=f"Summary {i}",
                topics=[],
                session_ids=[f"s{i}"],
                message_count=i,
                source="fallback",
            )
            store.append(ep)

        lines = store._file_path("bob").read_text().strip().splitlines()
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# EpisodeStore.get_recent()
# ---------------------------------------------------------------------------

class TestEpisodeStoreGetRecent:
    def test_get_recent_returns_newest_n(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        for i in range(7):
            store.append(Episode.create(
                user_id="carol",
                summary=f"Episode {i}",
                topics=[],
                session_ids=[f"s{i}"],
                message_count=i,
                source="fallback",
            ))

        recent = store.get_recent("carol", limit=3)
        assert len(recent) == 3
        # Should be the last 3
        assert recent[-1].summary == "Episode 6"
        assert recent[0].summary == "Episode 4"

    def test_get_recent_empty_file_returns_empty_list(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        # Create an empty file
        store._file_path("nobody").parent.mkdir(parents=True, exist_ok=True)
        store._file_path("nobody").write_text("")
        result = store.get_recent("nobody")
        assert result == []

    def test_get_recent_no_file_returns_empty_list(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        result = store.get_recent("nonexistent_user")
        assert result == []

    def test_get_recent_fewer_than_limit(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        store.append(Episode.create(
            user_id="dave",
            summary="Only one",
            topics=[],
            session_ids=["s0"],
            message_count=1,
            source="fallback",
        ))
        result = store.get_recent("dave", limit=10)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# EpisodeStore.search()
# ---------------------------------------------------------------------------

class TestEpisodeStoreSearch:
    def _make_store(self, tmp_path) -> EpisodeStore:
        store = EpisodeStore(base_dir=str(tmp_path))
        store.append(Episode.create(
            user_id="eve",
            summary="Wir haben über Python und GENUS gesprochen.",
            topics=["python", "genus"],
            session_ids=["s1"],
            message_count=5,
            source="llm",
        ))
        store.append(Episode.create(
            user_id="eve",
            summary="Docker-Container für den Raspberry Pi eingerichtet.",
            topics=["docker", "raspberry"],
            session_ids=["s2"],
            message_count=8,
            source="fallback",
        ))
        store.append(Episode.create(
            user_id="eve",
            summary="Neues Feature für den DevLoop besprochen.",
            topics=["devloop", "feature"],
            session_ids=["s3"],
            message_count=3,
            source="llm",
        ))
        return store

    def test_search_finds_keyword_in_summary(self, tmp_path):
        store = self._make_store(tmp_path)
        results = store.search("eve", keywords=["docker"])
        assert len(results) == 1
        assert "Docker" in results[0].summary

    def test_search_finds_keyword_in_topics(self, tmp_path):
        store = self._make_store(tmp_path)
        results = store.search("eve", keywords=["genus"])
        assert len(results) == 1
        assert "genus" in results[0].topics

    def test_search_case_insensitive(self, tmp_path):
        store = self._make_store(tmp_path)
        results = store.search("eve", keywords=["PYTHON"])
        assert len(results) >= 1

    def test_search_no_match_returns_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        results = store.search("eve", keywords=["kubernetes"])
        assert results == []

    def test_search_respects_limit(self, tmp_path):
        store = self._make_store(tmp_path)
        # "python" only matches one, but "e" would match all — use broad term
        results = store.search("eve", keywords=["besprochen", "eingerichtet", "gesprochen"], limit=2)
        assert len(results) <= 2

    def test_search_no_file_returns_empty(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        results = store.search("nobody", keywords=["anything"])
        assert results == []


# ---------------------------------------------------------------------------
# _file_path sanitisation
# ---------------------------------------------------------------------------

class TestFilePathSanitisation:
    def test_special_characters_in_user_id_are_sanitised(self, tmp_path):
        store = EpisodeStore(base_dir=str(tmp_path))
        path = store._file_path("user@example.com/../../evil")
        # Should not contain path traversal
        assert ".." not in str(path)
        assert path.parent == Path(str(tmp_path))
