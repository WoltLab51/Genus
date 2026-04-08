"""
Unit tests for GET /runs/{run_id}

Covers:
- 200 with correct fields for an existing run
- 404 for a non-existing run
- status "completed" when loop completed event is present
- status "failed" when loop failed event is present
- status "running" when loop started but no completed/failed
- status "unknown" when no loop event
- iterations correctly counted (fix_completed events)
- 403 without auth header
- artifacts_count and events_count correct
"""

import tempfile

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

TEST_API_KEY = "test-key"
TEST_RUN_ID = "test-run-001"
TEST_GOAL = "implement feature X"
TEST_REPO_ID = "WoltLab51/Genus"


def make_store(tmp_path):
    """Create a JsonlRunStore backed by a temp directory."""
    return JsonlRunStore(base_dir=str(tmp_path))


def make_client(run_store):
    """Return a TestClient configured with the given run_store."""
    app = create_app(api_key=TEST_API_KEY, run_store=run_store)
    return TestClient(app, raise_server_exceptions=False)


def make_auth_headers():
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


# ---------------------------------------------------------------------------
# 404 — Run not found
# ---------------------------------------------------------------------------


class TestRunStatusNotFound:
    def test_missing_run_returns_404(self, tmp_path):
        store = make_store(tmp_path)
        with make_client(store) as client:
            resp = client.get("/runs/nonexistent-run", headers=make_auth_headers())
        assert resp.status_code == 404

    def test_missing_run_detail_message(self, tmp_path):
        store = make_store(tmp_path)
        with make_client(store) as client:
            resp = client.get("/runs/nonexistent-run", headers=make_auth_headers())
        data = resp.json()
        assert "not found" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Auth checks
# ---------------------------------------------------------------------------


class TestRunStatusAuth:
    def test_no_auth_returns_401(self, tmp_path):
        store = make_store(tmp_path)
        with make_client(store) as client:
            resp = client.get("/runs/some-run")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, tmp_path):
        store = make_store(tmp_path)
        with make_client(store) as client:
            resp = client.get(
                "/runs/some-run",
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 200 — Happy path
# ---------------------------------------------------------------------------


class TestRunStatusHappyPath:
    def _setup_run(self, tmp_path, events=None, artifacts=None):
        """Create a run with given events and artifacts, return store."""
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL, repo_id=TEST_REPO_ID)
        for ev in (events or []):
            journal.log_event(**ev)
        for art in (artifacts or []):
            journal.save_artifact(**art)
        return store

    def test_existing_run_returns_200(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.status_code == 200

    def test_response_contains_run_id(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["run_id"] == TEST_RUN_ID

    def test_response_contains_goal(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["goal"] == TEST_GOAL

    def test_response_contains_repo_id(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["repo_id"] == TEST_REPO_ID

    def test_response_contains_created_at(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["created_at"] is not None

    def test_events_count_correct(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "loop start"},
            {"phase": "plan", "event_type": "decision", "summary": "planned"},
        ]
        store = self._setup_run(tmp_path, events=events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        data = resp.json()
        assert data["events_count"] == 2

    def test_events_count_zero_for_fresh_run(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["events_count"] == 0

    def test_artifacts_count_correct(self, tmp_path):
        artifacts = [
            {"phase": "plan", "artifact_type": "plan", "payload": {"steps": []}},
            {"phase": "test", "artifact_type": "test_report", "payload": {"passed": True}},
        ]
        store = self._setup_run(tmp_path, artifacts=artifacts)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["artifacts_count"] == 2

    def test_artifacts_count_zero_for_fresh_run(self, tmp_path):
        store = self._setup_run(tmp_path)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["artifacts_count"] == 0


# ---------------------------------------------------------------------------
# Status logic
# ---------------------------------------------------------------------------


class TestRunStatusLogic:
    def _setup_run_with_events(self, tmp_path, events):
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL)
        for ev in events:
            journal.log_event(**ev)
        return store

    def test_status_completed_on_loop_completed(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
            {"phase": "loop", "event_type": "completed", "summary": "c"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "completed"

    def test_status_failed_on_loop_failed(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
            {"phase": "loop", "event_type": "failed", "summary": "f"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "failed"

    def test_status_running_when_started_no_terminal(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
            {"phase": "plan", "event_type": "decision", "summary": "d"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "running"

    def test_status_unknown_when_no_loop_event(self, tmp_path):
        events = [
            {"phase": "plan", "event_type": "started", "summary": "s"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "unknown"

    def test_status_unknown_for_fresh_run_no_events(self, tmp_path):
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "unknown"

    def test_completed_takes_priority_over_failed(self, tmp_path):
        """If both completed and failed events exist, status should be completed."""
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
            {"phase": "loop", "event_type": "failed", "summary": "f"},
            {"phase": "loop", "event_type": "completed", "summary": "c"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Iterations
# ---------------------------------------------------------------------------


class TestRunStatusIterations:
    def _setup_run_with_events(self, tmp_path, events):
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL)
        for ev in events:
            journal.log_event(**ev)
        return store

    def test_iterations_zero_no_fix_events(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["iterations"] == 0

    def test_iterations_counts_fix_completed(self, tmp_path):
        events = [
            {"phase": "fix", "event_type": "fix_completed", "summary": "fix 1"},
            {"phase": "fix", "event_type": "fix_completed", "summary": "fix 2"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["iterations"] == 2

    def test_iterations_ignores_non_fix_completed(self, tmp_path):
        events = [
            {"phase": "fix", "event_type": "started", "summary": "fix start"},
            {"phase": "fix", "event_type": "fix_completed", "summary": "fix done"},
            {"phase": "plan", "event_type": "fix_completed", "summary": "wrong phase"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["iterations"] == 1


# ---------------------------------------------------------------------------
# current_phase
# ---------------------------------------------------------------------------


class TestRunStatusCurrentPhase:
    def _setup_run_with_events(self, tmp_path, events):
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL)
        for ev in events:
            journal.log_event(**ev)
        return store

    def test_current_phase_from_last_event(self, tmp_path):
        events = [
            {"phase": "loop", "event_type": "started", "summary": "s"},
            {"phase": "fix", "event_type": "fix_completed", "summary": "f"},
        ]
        store = self._setup_run_with_events(tmp_path, events)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["current_phase"] == "fix"

    def test_current_phase_none_when_no_events(self, tmp_path):
        store = make_store(tmp_path)
        journal = RunJournal(TEST_RUN_ID, store)
        journal.initialize(goal=TEST_GOAL)
        with make_client(store) as client:
            resp = client.get(f"/runs/{TEST_RUN_ID}", headers=make_auth_headers())
        assert resp.json()["current_phase"] is None
