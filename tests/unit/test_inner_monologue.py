"""Unit tests for genus.memory.inner_monologue — Phase 15a."""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from genus.memory.inner_monologue import (
    InnerMonologue,
    MonologueNote,
    _MAX_NOTE_CHARS,
    _NOTE_TTL_HOURS,
)


# ---------------------------------------------------------------------------
# MonologueNote — data model tests
# ---------------------------------------------------------------------------


class TestMonologueNoteModel:
    def test_to_dict_round_trip(self):
        now = datetime.now(timezone.utc)
        note = MonologueNote(user_id="user1", note="Test note", created_at=now)
        d = note.to_dict()
        restored = MonologueNote.from_dict(d)
        assert restored.user_id == note.user_id
        assert restored.note == note.note
        # Compare ISO strings to avoid microsecond precision issues
        assert restored.created_at.isoformat() == note.created_at.isoformat()

    def test_from_dict_with_string_created_at(self):
        data = {
            "user_id": "user1",
            "note": "Hello",
            "created_at": "2024-04-01T12:00:00+00:00",
        }
        note = MonologueNote.from_dict(data)
        assert note.user_id == "user1"
        assert note.note == "Hello"
        assert note.created_at.year == 2024

    def test_from_dict_missing_created_at_uses_now(self):
        data = {"user_id": "user1", "note": "No timestamp"}
        note = MonologueNote.from_dict(data)
        # Should default to now (not raise)
        assert note.created_at is not None
        assert isinstance(note.created_at, datetime)

    def test_is_expired_fresh_note(self):
        note = MonologueNote(user_id="user1", note="Fresh")
        assert not note.is_expired()

    def test_is_expired_old_note(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=_NOTE_TTL_HOURS + 1)
        note = MonologueNote(user_id="user1", note="Old", created_at=old_time)
        assert note.is_expired()

    def test_is_expired_near_ttl_boundary(self):
        # Well within TTL — definitely not expired
        recent_time = datetime.now(timezone.utc) - timedelta(hours=_NOTE_TTL_HOURS - 1)
        note = MonologueNote(user_id="user1", note="Recent", created_at=recent_time)
        assert not note.is_expired()


# ---------------------------------------------------------------------------
# InnerMonologue — CRUD tests
# ---------------------------------------------------------------------------


class TestInnerMonologueSet:
    def test_set_creates_jsonl_file(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Test note")
        file = tmp_path / "user1.jsonl"
        assert file.exists()

    def test_set_writes_valid_json(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Hello world")
        file = tmp_path / "user1.jsonl"
        lines = [l for l in file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["user_id"] == "user1"
        assert data["note"] == "Hello world"

    def test_set_returns_monologue_note(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        result = im.set("user1", "Note content")
        assert isinstance(result, MonologueNote)
        assert result.note == "Note content"
        assert result.user_id == "user1"

    def test_set_truncates_long_note(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        long_note = "X" * 500
        result = im.set("user1", long_note)
        assert len(result.note) == _MAX_NOTE_CHARS
        assert result.note == "X" * _MAX_NOTE_CHARS

    def test_set_strips_whitespace(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        result = im.set("user1", "   trimmed   ")
        assert result.note == "trimmed"

    def test_set_empty_note_is_noop(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        result = im.set("user1", "   ")  # all whitespace → empty after strip
        assert result.note == ""
        file = tmp_path / "user1.jsonl"
        assert not file.exists()  # nothing written

    def test_set_new_note_overwrites_previous(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "First note")
        im.set("user1", "Second note")
        file = tmp_path / "user1.jsonl"
        lines = [l for l in file.read_text().splitlines() if l.strip()]
        # Write mode: only the latest note is kept in the file
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["note"] == "Second note"


class TestInnerMonologueGetCurrent:
    def test_get_current_no_file_returns_none(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        result = im.get_current("nonexistent_user")
        assert result is None

    def test_get_current_fresh_note_returns_text(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Active note")
        result = im.get_current("user1")
        assert result == "Active note"

    def test_get_current_expired_note_returns_none(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        # Write expired note directly
        old_time = datetime.now(timezone.utc) - timedelta(hours=_NOTE_TTL_HOURS + 1)
        expired = MonologueNote(
            user_id="user1",
            note="Expired note",
            created_at=old_time,
        )
        file = tmp_path / "user1.jsonl"
        file.write_text(json.dumps(expired.to_dict()) + "\n", encoding="utf-8")

        result = im.get_current("user1")
        assert result is None

    def test_get_current_returns_latest_note(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "First note")
        im.set("user1", "Second note (newer)")
        result = im.get_current("user1")
        assert result == "Second note (newer)"

    def test_get_current_latest_fresh_after_expired(self, tmp_path):
        """Latest note is fresh even if file also contains expired notes."""
        im = InnerMonologue(base_dir=tmp_path)
        # Write expired note first
        old_time = datetime.now(timezone.utc) - timedelta(hours=_NOTE_TTL_HOURS + 1)
        expired = MonologueNote(user_id="user1", note="Old", created_at=old_time)
        file = tmp_path / "user1.jsonl"
        file.write_text(json.dumps(expired.to_dict()) + "\n", encoding="utf-8")
        # Append fresh note
        im.set("user1", "Fresh note")
        result = im.get_current("user1")
        assert result == "Fresh note"


class TestInnerMonologueClear:
    def test_clear_removes_file(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Note")
        file = tmp_path / "user1.jsonl"
        assert file.exists()
        im.clear("user1")
        assert not file.exists()

    def test_clear_nonexistent_no_crash(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        # Should not raise
        im.clear("nonexistent_user")

    def test_after_clear_get_current_returns_none(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Note")
        im.clear("user1")
        assert im.get_current("user1") is None


class TestInnerMonologueGetAllActive:
    def test_get_all_active_empty_dir(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        result = im.get_all_active()
        assert result == []

    def test_get_all_active_nonexistent_dir(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path / "nonexistent")
        result = im.get_all_active()
        assert result == []

    def test_get_all_active_returns_fresh_notes(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        im.set("user1", "Note for user1")
        im.set("user2", "Note for user2")
        result = im.get_all_active()
        user_ids = {n.user_id for n in result}
        assert "user1" in user_ids
        assert "user2" in user_ids

    def test_get_all_active_excludes_expired(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        # Fresh note for user1
        im.set("user1", "Fresh")
        # Expired note for user2
        old_time = datetime.now(timezone.utc) - timedelta(hours=_NOTE_TTL_HOURS + 1)
        expired = MonologueNote(user_id="user2", note="Old", created_at=old_time)
        file = tmp_path / "user2.jsonl"
        file.write_text(json.dumps(expired.to_dict()) + "\n", encoding="utf-8")

        result = im.get_all_active()
        user_ids = {n.user_id for n in result}
        assert "user1" in user_ids
        assert "user2" not in user_ids


# ---------------------------------------------------------------------------
# InnerMonologue — file path sanitisation
# ---------------------------------------------------------------------------


class TestInnerMonologueFilePath:
    def test_alphanumeric_user_id_unchanged(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        path = im._file_path("user123")
        assert path.name == "user123.jsonl"

    def test_special_chars_replaced_with_underscore(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        path = im._file_path("user@domain.com")
        assert "@" not in path.name
        assert "." not in path.stem
        assert path.suffix == ".jsonl"

    def test_hyphens_and_underscores_allowed(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        path = im._file_path("user-id_123")
        assert path.name == "user-id_123.jsonl"

    def test_sanitised_path_is_under_base_dir(self, tmp_path):
        im = InnerMonologue(base_dir=tmp_path)
        path = im._file_path("some.user")
        assert path.parent == tmp_path
