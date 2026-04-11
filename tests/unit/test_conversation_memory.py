"""Unit tests for ConversationMemory — Phase 13."""

import json
import pytest

from genus.conversation.conversation_agent import ConversationMemory


class TestConversationMemory:
    def test_add_user_and_assistant(self, tmp_path):
        mem = ConversationMemory("sess-001", max_history=20, base_dir=tmp_path)
        mem.add_user("Hey GENUS")
        mem.add_assistant("Hey! Ich bin hier.")

        ctx = mem.get_context()
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert ctx[0]["content"] == "Hey GENUS"
        assert ctx[1]["role"] == "assistant"
        assert ctx[1]["content"] == "Hey! Ich bin hier."

    def test_persistence_reload(self, tmp_path):
        """Messages written to JSONL are reloaded on re-instantiation."""
        mem = ConversationMemory("sess-persist", max_history=20, base_dir=tmp_path)
        mem.add_user("Erste Nachricht")
        mem.add_assistant("Erste Antwort")

        # New instance reading from same dir
        mem2 = ConversationMemory("sess-persist", max_history=20, base_dir=tmp_path)
        ctx = mem2.get_context()
        assert len(ctx) == 2
        assert ctx[0]["content"] == "Erste Nachricht"
        assert ctx[1]["content"] == "Erste Antwort"

    def test_max_history_limits_context(self, tmp_path):
        """max_history=3 → only last 3 messages returned by get_context()."""
        mem = ConversationMemory("sess-max", max_history=3, base_dir=tmp_path)
        for i in range(5):
            mem.add_user(f"Nachricht {i}")

        ctx = mem.get_context()
        assert len(ctx) == 3
        assert ctx[0]["content"] == "Nachricht 2"
        assert ctx[-1]["content"] == "Nachricht 4"

    def test_empty_session_returns_empty_context(self, tmp_path):
        """Freshly created memory returns empty context."""
        mem = ConversationMemory("sess-empty", max_history=20, base_dir=tmp_path)
        assert mem.get_context() == []

    def test_jsonl_file_created(self, tmp_path):
        """A JSONL file is created after adding a message."""
        mem = ConversationMemory("sess-file", max_history=20, base_dir=tmp_path)
        mem.add_user("Test")
        jsonl_file = tmp_path / "sess-file.jsonl"
        assert jsonl_file.exists()

    def test_jsonl_file_contains_valid_json(self, tmp_path):
        """Each line in the JSONL file is valid JSON."""
        mem = ConversationMemory("sess-json", max_history=20, base_dir=tmp_path)
        mem.add_user("Hallo")
        mem.add_assistant("Wie kann ich helfen?")

        jsonl_file = tmp_path / "sess-json.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "role" in obj
            assert "content" in obj
            assert "timestamp" in obj

    def test_max_history_in_file_but_limited_context(self, tmp_path):
        """All messages are persisted; only max_history are in context."""
        mem = ConversationMemory("sess-allsave", max_history=2, base_dir=tmp_path)
        for i in range(4):
            mem.add_user(f"msg {i}")

        # File has all 4
        jsonl_file = tmp_path / "sess-allsave.jsonl"
        lines = jsonl_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4

        # Context is limited to 2
        assert len(mem.get_context()) == 2
