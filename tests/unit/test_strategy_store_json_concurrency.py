"""Test StrategyStoreJson thread-safety."""

import concurrent.futures
import tempfile
import threading
from pathlib import Path

from genus.strategy.store_json import StrategyStoreJson


def test_concurrent_set_failure_class_weight_no_lost_updates():
    """Two threads writing different playbooks concurrently — both updates survive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))

        errors = []

        def write_weight(playbook, value):
            try:
                store.set_failure_class_weight("test_failure", playbook, value)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write_weight, args=("playbook_a", 5))
        t2 = threading.Thread(target=write_weight, args=("playbook_b", -3))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        assert store.get_failure_class_weight("test_failure", "playbook_a") == 5
        assert store.get_failure_class_weight("test_failure", "playbook_b") == -3


def test_concurrent_add_learning_entry_no_lost_entries():
    """Multiple threads adding learning entries concurrently — all entries survive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = StrategyStoreJson(base_dir=str(Path(tmpdir) / "strategy"))

        def add_entry(run_id):
            store.add_learning_entry(
                run_id=run_id,
                failure_class="test_failure",
                root_cause_hint=None,
                selected_playbook="playbook_a",
                outcome_score=80,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(add_entry, f"run_{i}") for i in range(20)]
            concurrent.futures.wait(futures)

        history = store.get_learning_history(failure_class="test_failure")
        assert len(history) == 20, f"Expected 20 entries, got {len(history)}"
