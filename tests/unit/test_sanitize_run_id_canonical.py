"""Tests that sanitize_run_id is the same function in both modules."""
import pytest
from genus.memory.store_jsonl import sanitize_run_id as sanitize_store
from genus.memory.jsonl_event_store import sanitize_run_id as sanitize_event


def test_same_behavior_normal():
    assert sanitize_store("my-run-001") == sanitize_event("my-run-001")


def test_same_behavior_special_chars():
    assert sanitize_store("run/with spaces!") == sanitize_event("run/with spaces!")


def test_same_behavior_empty():
    assert sanitize_store("") == sanitize_event("")


def test_traversal_both_raise():
    with pytest.raises(ValueError):
        sanitize_store("../evil")
    with pytest.raises(ValueError):
        sanitize_event("../evil")


def test_same_function_object():
    """sanitize_run_id is the same function object in both modules."""
    assert sanitize_store is sanitize_event
