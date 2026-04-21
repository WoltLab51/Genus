"""Unit tests for POST /v1/memory/search API endpoint.

Tests cover:
- Keyword search across facts
- Keyword search across episodes
- Combined search (facts + episodes)
- include_facts / include_episodes flags
- Auth guards (401 / 403)
- Missing keyword / query returns 422
- Query string tokenisation
"""

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.memory.fact_store import SemanticFact, SemanticFactStore
from genus.memory.episode_store import Episode, EpisodeStore


TEST_KEY = "test-search-key"
AUTH = {"Authorization": f"Bearer {TEST_KEY}"}


def _make_client(tmp_path, *, seed_facts=True, seed_episodes=True):
    """Create a TestClient with seeded fact and episode stores."""
    app = create_app(api_key=TEST_KEY)

    fact_store = SemanticFactStore(base_dir=str(tmp_path / "facts"))
    if seed_facts:
        fact_store.upsert(
            SemanticFact.create(
                user_id="testuser",
                key="llm_preference",
                value="ollama_lokal",
                source="test",
                scope="private:testuser",
                created_by="test",
            )
        )
        fact_store.upsert(
            SemanticFact.create(
                user_id="testuser",
                key="favorite_language",
                value="Python",
                source="test",
                scope="private:testuser",
                created_by="test",
            )
        )

    episode_store = EpisodeStore(base_dir=str(tmp_path / "episodes"))
    if seed_episodes:
        episode_store.append(
            Episode.create(
                user_id="testuser",
                summary="Diskussion über Python und FastAPI",
                topics=["python", "fastapi"],
                session_ids=["s1"],
                message_count=5,
                source="test",
                scope="private:testuser",
                created_by="test",
            )
        )
        episode_store.append(
            Episode.create(
                user_id="testuser",
                summary="Planung des Familienurlaubs",
                topics=["urlaub", "family"],
                session_ids=["s2"],
                message_count=10,
                source="test",
                scope="private:testuser",
                created_by="test",
            )
        )

    app.state.fact_store = fact_store
    app.state.episode_store = episode_store
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


class TestSearchAuth:
    def test_no_auth_returns_401(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "python", "user_id": "testuser"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSearchValidation:
    def test_empty_keywords_and_no_query_returns_422(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"keywords": [], "user_id": "testuser"},
                headers=AUTH,
            )
        assert resp.status_code == 422

    def test_query_only_whitespace_returns_422(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "   ", "user_id": "testuser"},
                headers=AUTH,
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Fact search
# ---------------------------------------------------------------------------


class TestFactSearch:
    def test_finds_fact_by_value(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "ollama", "user_id": "testuser"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["facts"]) >= 1
        assert any("ollama" in f["value"].lower() for f in data["facts"])

    def test_finds_fact_by_key(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "llm_preference", "user_id": "testuser"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert any(f["key"] == "llm_preference" for f in data["facts"])

    def test_no_fact_match_returns_empty_list(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "xyzzy-no-match", "user_id": "testuser"},
                headers=AUTH,
            )
        data = resp.json()
        assert data["facts"] == []

    def test_include_facts_false_skips_facts(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={
                    "query": "ollama",
                    "user_id": "testuser",
                    "include_facts": False,
                },
                headers=AUTH,
            )
        data = resp.json()
        assert data["facts"] == []


# ---------------------------------------------------------------------------
# Episode search
# ---------------------------------------------------------------------------


class TestEpisodeSearch:
    def test_finds_episode_by_summary(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "FastAPI", "user_id": "testuser"},
                headers=AUTH,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["episodes"]) >= 1
        assert any("FastAPI" in ep["summary"] for ep in data["episodes"])

    def test_finds_episode_by_topic(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "urlaub", "user_id": "testuser"},
                headers=AUTH,
            )
        data = resp.json()
        assert len(data["episodes"]) >= 1

    def test_include_episodes_false_skips_episodes(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={
                    "query": "FastAPI",
                    "user_id": "testuser",
                    "include_episodes": False,
                },
                headers=AUTH,
            )
        data = resp.json()
        assert data["episodes"] == []


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


class TestSearchResponseStructure:
    def test_response_has_required_keys(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "python", "user_id": "testuser"},
                headers=AUTH,
            )
        data = resp.json()
        assert "facts" in data
        assert "episodes" in data
        assert "query" in data
        assert "keywords" in data

    def test_keywords_field_contains_tokens(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={"query": "python fastapi", "user_id": "testuser"},
                headers=AUTH,
            )
        data = resp.json()
        assert "python" in data["keywords"]
        assert "fastapi" in data["keywords"]

    def test_explicit_keywords_merged_with_query(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={
                    "query": "python",
                    "keywords": ["ollama"],
                    "user_id": "testuser",
                },
                headers=AUTH,
            )
        data = resp.json()
        assert "python" in data["keywords"]
        assert "ollama" in data["keywords"]

    def test_duplicate_keywords_deduplicated(self, tmp_path):
        with _make_client(tmp_path) as client:
            resp = client.post(
                "/v1/memory/search",
                json={
                    "query": "python python",
                    "keywords": ["python"],
                    "user_id": "testuser",
                },
                headers=AUTH,
            )
        data = resp.json()
        assert data["keywords"].count("python") == 1
