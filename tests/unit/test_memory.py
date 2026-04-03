"""Unit tests for MemoryStore (in-memory KV)."""

import pytest
from genus.storage.memory import MemoryStore


class TestMemoryStore:

    def test_set_get(self):
        s = MemoryStore()
        s.set("ns", "k", "v")
        assert s.get("ns", "k") == "v"

    def test_get_default(self):
        s = MemoryStore()
        assert s.get("ns", "missing", "d") == "d"

    def test_get_all(self):
        s = MemoryStore()
        s.set("ns", "a", 1)
        s.set("ns", "b", 2)
        assert s.get_all("ns") == {"a": 1, "b": 2}

    def test_delete(self):
        s = MemoryStore()
        s.set("ns", "k", "v")
        assert s.delete("ns", "k") is True
        assert s.get("ns", "k") is None

    def test_delete_missing(self):
        s = MemoryStore()
        assert s.delete("ns", "nope") is False

    def test_clear_namespace(self):
        s = MemoryStore()
        s.set("ns", "a", 1)
        s.set("ns", "b", 2)
        s.clear_namespace("ns")
        assert s.get_all("ns") == {}

    def test_history(self):
        s = MemoryStore()
        s.set("ns", "a", 1)
        s.set("ns", "b", 2)
        h = s.history(limit=10)
        assert len(h) == 2
        assert h[0]["key"] == "a"

    def test_history_limit_cap(self):
        s = MemoryStore()
        s._max_history = 3
        for i in range(10):
            s.set("ns", str(i), i)
        assert len(s.history(limit=100)) == 3
