"""
Tests for genus.memory.fact_store — Phase 14b
"""

import pytest
from pathlib import Path

from genus.memory.fact_store import (
    ConflictDetectedError,
    SemanticFact,
    SemanticFactStore,
)


# ---------------------------------------------------------------------------
# SemanticFact round-trip
# ---------------------------------------------------------------------------

class TestSemanticFactRoundTrip:
    def test_to_dict_from_dict_roundtrip(self):
        fact = SemanticFact.create(
            user_id="alice",
            key="llm_preference",
            value="ollama_lokal",
            source="ConversationAgent",
            notes="Bevorzugt lokales LLM.",
        )
        restored = SemanticFact.from_dict(fact.to_dict())
        assert restored.fact_id == fact.fact_id
        assert restored.user_id == fact.user_id
        assert restored.key == fact.key
        assert restored.value == fact.value
        assert restored.source == fact.source
        assert restored.created_at == fact.created_at
        assert restored.updated_at == fact.updated_at
        assert restored.notes == fact.notes

    def test_from_dict_defaults(self):
        data = {
            "fact_id": "abc",
            "user_id": "bob",
            "key": "sprache",
            "value": "deutsch",
            "created_at": "2026-04-01T00:00:00+00:00",
        }
        fact = SemanticFact.from_dict(data)
        assert fact.source == ""
        assert fact.notes is None
        assert fact.updated_at == data["created_at"]


# ---------------------------------------------------------------------------
# SemanticFactStore.upsert()
# ---------------------------------------------------------------------------

class TestSemanticFactStoreUpsert:
    def test_upsert_stores_new_fact(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        fact = SemanticFact.create(user_id="alice", key="sprache", value="deutsch")
        stored = store.upsert(fact)
        assert stored.key == "sprache"
        assert stored.value == "deutsch"

        retrieved = store.get("alice", "sprache")
        assert retrieved is not None
        assert retrieved.value == "deutsch"

    def test_upsert_no_conflict_same_value(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        fact = SemanticFact.create(user_id="alice", key="sprache", value="deutsch")
        store.upsert(fact)
        # Same value again — should not raise
        fact2 = SemanticFact.create(user_id="alice", key="sprache", value="deutsch")
        stored = store.upsert(fact2)
        assert stored.value == "deutsch"

    def test_upsert_raises_conflict_on_different_value(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        fact = SemanticFact.create(user_id="alice", key="redis", value="nein")
        store.upsert(fact)

        fact2 = SemanticFact.create(user_id="alice", key="redis", value="ja")
        with pytest.raises(ConflictDetectedError) as exc_info:
            store.upsert(fact2)

        err = exc_info.value
        assert err.key == "redis"
        assert err.existing_value == "nein"
        assert err.new_value == "ja"


# ---------------------------------------------------------------------------
# ConflictDetectedError attributes
# ---------------------------------------------------------------------------

class TestConflictDetectedError:
    def test_error_has_correct_attributes(self):
        err = ConflictDetectedError(key="foo", existing_value="bar", new_value="baz")
        assert err.key == "foo"
        assert err.existing_value == "bar"
        assert err.new_value == "baz"
        assert "foo" in str(err)


# ---------------------------------------------------------------------------
# SemanticFactStore.force_update()
# ---------------------------------------------------------------------------

class TestSemanticFactStoreForceUpdate:
    def test_force_update_overwrites_without_conflict(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        fact = SemanticFact.create(user_id="bob", key="redis", value="nein")
        store.upsert(fact)

        fact2 = SemanticFact.create(user_id="bob", key="redis", value="ja")
        stored = store.force_update(fact2)
        assert stored.value == "ja"

        retrieved = store.get("bob", "redis")
        assert retrieved is not None
        assert retrieved.value == "ja"


# ---------------------------------------------------------------------------
# SemanticFactStore.get()
# ---------------------------------------------------------------------------

class TestSemanticFactStoreGet:
    def test_get_returns_none_for_unknown_key(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        result = store.get("nobody", "unknown_key")
        assert result is None

    def test_get_returns_none_for_unknown_user(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        result = store.get("no_such_user", "any_key")
        assert result is None


# ---------------------------------------------------------------------------
# SemanticFactStore.get_all()
# ---------------------------------------------------------------------------

class TestSemanticFactStoreGetAll:
    def test_get_all_returns_all_facts_as_dict(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        store.upsert(SemanticFact.create(user_id="carol", key="sprache", value="deutsch"))
        store.upsert(SemanticFact.create(user_id="carol", key="stil", value="kurz"))

        all_facts = store.get_all("carol")
        assert "sprache" in all_facts
        assert "stil" in all_facts
        assert all_facts["sprache"].value == "deutsch"
        assert all_facts["stil"].value == "kurz"

    def test_get_all_returns_empty_dict_for_unknown_user(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        result = store.get_all("no_such_user")
        assert result == {}


# ---------------------------------------------------------------------------
# Last-write-wins semantics
# ---------------------------------------------------------------------------

class TestLastWriteWins:
    def test_last_write_wins_for_same_key(self, tmp_path):
        """After force_update, get() returns the latest value."""
        store = SemanticFactStore(base_dir=str(tmp_path))
        fact_v1 = SemanticFact.create(user_id="dave", key="color", value="blue")
        store.upsert(fact_v1)

        fact_v2 = SemanticFact.create(user_id="dave", key="color", value="green")
        store.force_update(fact_v2)

        result = store.get("dave", "color")
        assert result is not None
        assert result.value == "green"

    def test_multiple_keys_independent(self, tmp_path):
        store = SemanticFactStore(base_dir=str(tmp_path))
        store.upsert(SemanticFact.create(user_id="eve", key="a", value="1"))
        store.upsert(SemanticFact.create(user_id="eve", key="b", value="2"))
        store.force_update(SemanticFact.create(user_id="eve", key="a", value="updated"))

        assert store.get("eve", "a").value == "updated"
        assert store.get("eve", "b").value == "2"
