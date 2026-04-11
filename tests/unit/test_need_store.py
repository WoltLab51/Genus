"""
Unit tests for genus.growth.need_store (NeedStore)

Verifies:
- save() writes a JSONL upsert entry
- load_all() returns an empty dict when no files exist
- load_all() correctly reconstructs state from JSONL
- dismiss() writes a dismiss event
- load_all() after dismiss: dismissed need not in result
- snapshot() writes a JSON snapshot
- load_all() uses snapshot + subsequent JSONL entries
- All tests use tmp_path
"""

import json

import pytest

from genus.growth.need_record import NeedRecord
from genus.growth.need_store import NeedStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path, snapshot_interval: int = 50) -> NeedStore:
    return NeedStore(base_dir=tmp_path, snapshot_interval=snapshot_interval)


def _make_record(domain: str = "system", need_desc: str = "run_failure", trigger_count: int = 1) -> NeedRecord:
    record = NeedRecord(domain=domain, need_description=need_desc)
    record.trigger_count = trigger_count
    return record


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------


class TestNeedStoreSave:
    def test_save_creates_jsonl_file(self, tmp_path):
        """save() creates the JSONL file when it does not exist."""
        store = _make_store(tmp_path)
        record = _make_record()
        store.save(record)

        jsonl_path = tmp_path / "needs.jsonl"
        assert jsonl_path.exists()

    def test_save_writes_upsert_event(self, tmp_path):
        """save() writes an upsert event with correct fields."""
        store = _make_store(tmp_path)
        record = _make_record(domain="quality", need_desc="low_quality_score", trigger_count=3)
        store.save(record)

        jsonl_path = tmp_path / "needs.jsonl"
        entry = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
        assert entry["event"] == "upsert"
        assert entry["domain"] == "quality"
        assert entry["need_description"] == "low_quality_score"
        assert entry["trigger_count"] == 3

    def test_save_multiple_records_appends_lines(self, tmp_path):
        """Multiple save() calls append multiple lines to the JSONL."""
        store = _make_store(tmp_path)
        store.save(_make_record(domain="system", need_desc="run_failure"))
        store.save(_make_record(domain="quality", need_desc="low_quality_score"))

        jsonl_path = tmp_path / "needs.jsonl"
        lines = [l for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_save_triggers_snapshot_after_interval(self, tmp_path):
        """save() triggers an automatic snapshot after snapshot_interval writes."""
        store = _make_store(tmp_path, snapshot_interval=2)

        store.save(_make_record(need_desc="need_1"))
        assert not (tmp_path / "needs_snapshot.json").exists()

        store.save(_make_record(need_desc="need_2"))
        assert (tmp_path / "needs_snapshot.json").exists()


# ---------------------------------------------------------------------------
# load_all()
# ---------------------------------------------------------------------------


class TestNeedStoreLoadAll:
    def test_load_all_empty_when_no_files(self, tmp_path):
        """load_all() returns empty dict when neither JSONL nor snapshot exists."""
        store = _make_store(tmp_path)
        result = store.load_all()
        assert result == {}

    def test_load_all_reconstructs_from_jsonl(self, tmp_path):
        """load_all() reconstructs a record correctly from JSONL."""
        store = _make_store(tmp_path)
        record = _make_record(domain="system", need_desc="run_failure", trigger_count=3)
        store.save(record)

        store2 = _make_store(tmp_path)
        result = store2.load_all()

        assert ("system", "run_failure") in result
        assert result[("system", "run_failure")].trigger_count == 3
        assert result[("system", "run_failure")].domain == "system"

    def test_load_all_returns_latest_state_for_same_key(self, tmp_path):
        """load_all() reflects the most recent upsert for duplicate keys."""
        store = _make_store(tmp_path)
        record_v1 = _make_record(trigger_count=1)
        record_v2 = _make_record(trigger_count=5)
        store.save(record_v1)
        store.save(record_v2)

        store2 = _make_store(tmp_path)
        result = store2.load_all()
        assert result[("system", "run_failure")].trigger_count == 5

    def test_load_all_preserves_status(self, tmp_path):
        """load_all() preserves the status field of stored records."""
        store = _make_store(tmp_path)
        record = _make_record(trigger_count=2)
        record.status = "queued"
        store.save(record)

        store2 = _make_store(tmp_path)
        result = store2.load_all()
        assert result[("system", "run_failure")].status == "queued"


# ---------------------------------------------------------------------------
# dismiss()
# ---------------------------------------------------------------------------


class TestNeedStoreDismiss:
    def test_dismiss_writes_dismiss_event(self, tmp_path):
        """dismiss() writes a dismiss event to the JSONL."""
        store = _make_store(tmp_path)
        store.save(_make_record(domain="quality", need_desc="low_quality_score"))
        store.dismiss("quality", "low_quality_score")

        jsonl_path = tmp_path / "needs.jsonl"
        lines = [json.loads(l) for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        dismiss_events = [l for l in lines if l["event"] == "dismiss"]

        assert len(dismiss_events) == 1
        assert dismiss_events[0]["domain"] == "quality"
        assert dismiss_events[0]["need_description"] == "low_quality_score"

    def test_dismiss_event_has_timestamp(self, tmp_path):
        """dismiss() event includes a timestamp field."""
        store = _make_store(tmp_path)
        store.save(_make_record())
        store.dismiss("system", "run_failure")

        jsonl_path = tmp_path / "needs.jsonl"
        lines = [json.loads(l) for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        dismiss_event = next(l for l in lines if l["event"] == "dismiss")
        assert "timestamp" in dismiss_event

    def test_load_all_excludes_dismissed_need(self, tmp_path):
        """load_all() does not include needs that have been dismissed."""
        store = _make_store(tmp_path)
        store.save(_make_record(domain="quality", need_desc="low_quality_score"))
        store.dismiss("quality", "low_quality_score")

        store2 = _make_store(tmp_path)
        result = store2.load_all()
        assert ("quality", "low_quality_score") not in result

    def test_load_all_keeps_other_needs_after_dismiss(self, tmp_path):
        """load_all() still returns undismissed needs after a dismiss event."""
        store = _make_store(tmp_path)
        store.save(_make_record(domain="quality", need_desc="low_quality_score"))
        store.save(_make_record(domain="system", need_desc="run_failure"))
        store.dismiss("quality", "low_quality_score")

        store2 = _make_store(tmp_path)
        result = store2.load_all()
        assert ("quality", "low_quality_score") not in result
        assert ("system", "run_failure") in result


# ---------------------------------------------------------------------------
# snapshot()
# ---------------------------------------------------------------------------


class TestNeedStoreSnapshot:
    def test_snapshot_creates_file(self, tmp_path):
        """snapshot() creates needs_snapshot.json."""
        store = _make_store(tmp_path)
        store.save(_make_record())
        store.snapshot()

        assert (tmp_path / "needs_snapshot.json").exists()

    def test_snapshot_contains_records(self, tmp_path):
        """snapshot() writes a JSON file with a records list."""
        store = _make_store(tmp_path)
        store.save(_make_record(domain="system", need_desc="run_failure"))
        store.snapshot()

        snap = json.loads((tmp_path / "needs_snapshot.json").read_text(encoding="utf-8"))
        assert "records" in snap
        need_descs = [r["need_description"] for r in snap["records"]]
        assert "run_failure" in need_descs

    def test_snapshot_records_jsonl_line_count(self, tmp_path):
        """snapshot() stores the current JSONL line count for incremental loading."""
        store = _make_store(tmp_path)
        store.save(_make_record(need_desc="need_1"))
        store.save(_make_record(need_desc="need_2"))
        store.snapshot()

        snap = json.loads((tmp_path / "needs_snapshot.json").read_text(encoding="utf-8"))
        assert snap["jsonl_line_count"] == 2

    def test_snapshot_resets_write_count(self, tmp_path):
        """snapshot() resets the internal write counter."""
        store = _make_store(tmp_path, snapshot_interval=3)
        store.save(_make_record(need_desc="need_1"))
        store.save(_make_record(need_desc="need_2"))
        store.snapshot()

        assert store._write_count == 0

    def test_load_all_uses_snapshot_plus_subsequent_jsonl(self, tmp_path):
        """load_all() loads snapshot as base state and replays post-snapshot JSONL entries."""
        store = _make_store(tmp_path)

        # Save record1 and take an explicit snapshot.
        record1 = _make_record(domain="system", need_desc="run_failure", trigger_count=2)
        store.save(record1)
        store.snapshot()  # snapshot: line_count=1, records=[record1]

        # Save record2 after the snapshot.
        record2 = _make_record(domain="quality", need_desc="low_quality_score", trigger_count=1)
        store.save(record2)

        # Load on a fresh instance — should have both records.
        store2 = _make_store(tmp_path)
        result = store2.load_all()

        assert ("system", "run_failure") in result
        assert ("quality", "low_quality_score") in result
        assert result[("system", "run_failure")].trigger_count == 2
        assert result[("quality", "low_quality_score")].trigger_count == 1

    def test_load_all_applies_dismiss_after_snapshot(self, tmp_path):
        """load_all() correctly applies dismiss events that come after the snapshot."""
        store = _make_store(tmp_path)

        store.save(_make_record(domain="system", need_desc="run_failure"))
        store.snapshot()  # snapshot has run_failure; line_count=1

        store.dismiss("system", "run_failure")  # written after snapshot

        store2 = _make_store(tmp_path)
        result = store2.load_all()
        assert ("system", "run_failure") not in result
