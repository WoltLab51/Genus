"""
Integration tests for TesterAgent with real pytest execution (Phase B).

These tests run actual pytest inside a sandbox and verify that:
- Passing tests are correctly detected
- Failing tests are correctly detected with structured failure details
"""

import asyncio
import pytest
from pathlib import Path

from genus.communication.message_bus import MessageBus
from genus.core.run import new_run_id
from genus.workspace.workspace import RunWorkspace
from genus.dev.agents.tester_agent import TesterAgent
from genus.dev import events, topics


def _make_workspace(tmp_path: Path) -> RunWorkspace:
    run_id = new_run_id()
    workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)
    workspace.ensure_dirs()
    # Minimal git init so sandbox_run can resolve the workspace
    import subprocess
    subprocess.run(["git", "init"], cwd=workspace.repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=workspace.repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=workspace.repo_dir, check=True, capture_output=True)
    return workspace


@pytest.mark.asyncio
async def test_tester_agent_real_pytest_all_pass(tmp_path):
    """TesterAgent runs real pytest and reports all tests passing."""
    workspace = _make_workspace(tmp_path)
    repo_dir = workspace.repo_dir

    # Write a simple module
    (repo_dir / "mymodule.py").write_text(
        "def add(a, b):\n    return a + b\n"
    )

    # Write passing tests
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").touch()
    (tests_dir / "test_mymodule.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))\n"
        "from mymodule import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n\n"
        "def test_add_negative():\n"
        "    assert add(-1, 1) == 0\n"
    )

    bus = MessageBus()
    completed = []
    failed = []

    async def on_completed(msg):
        if msg.metadata.get("run_id") == workspace.run_id:
            completed.append(msg.payload.get("report", {}))

    async def on_failed(msg):
        if msg.metadata.get("run_id") == workspace.run_id:
            failed.append(msg.payload)

    bus.subscribe(topics.DEV_TEST_COMPLETED, "tracker-c", on_completed)
    bus.subscribe(topics.DEV_TEST_FAILED, "tracker-f", on_failed)

    tester = TesterAgent(
        bus,
        agent_id="tester-int",
        workspace=workspace,
        test_argv=["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
    )
    tester.start()

    try:
        req = events.dev_test_requested_message(workspace.run_id, "test-sender")
        # Ensure phase_id is present (added by event factory)
        await bus.publish(req)
        await asyncio.sleep(10.0)
    finally:
        tester.stop()

    assert len(failed) == 0, "Should not have published failed: {}".format(failed)
    assert len(completed) == 1, "Should have published completed"

    report = completed[0]
    assert report["status"] == "passed", "Status should be 'passed'"
    assert report["passed"] == 2, "Should have 2 passed tests"
    assert report["failed"] == 0, "Should have 0 failed tests"
    assert report["failures"] == [], "No failures expected"
    assert report["exit_code"] == 0


@pytest.mark.asyncio
async def test_tester_agent_real_pytest_catches_failure(tmp_path):
    """TesterAgent runs real pytest and detects a real test failure."""
    workspace = _make_workspace(tmp_path)
    repo_dir = workspace.repo_dir

    # Write a buggy module
    (repo_dir / "buggy.py").write_text(
        "def multiply(a, b):\n"
        "    return a + b  # BUG: should be *\n"
    )

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").touch()
    (tests_dir / "test_buggy.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))\n"
        "from buggy import multiply\n\n"
        "def test_multiply():\n"
        "    assert multiply(3, 4) == 12  # fails because of the bug\n"
    )

    bus = MessageBus()
    completed = []
    failed_msgs = []

    async def on_completed(msg):
        if msg.metadata.get("run_id") == workspace.run_id:
            completed.append(msg.payload.get("report", {}))

    async def on_failed(msg):
        if msg.metadata.get("run_id") == workspace.run_id:
            failed_msgs.append(msg.payload)

    bus.subscribe(topics.DEV_TEST_COMPLETED, "tracker-c", on_completed)
    bus.subscribe(topics.DEV_TEST_FAILED, "tracker-f", on_failed)

    tester = TesterAgent(
        bus,
        agent_id="tester-int-fail",
        workspace=workspace,
        test_argv=["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
    )
    tester.start()

    try:
        req = events.dev_test_requested_message(workspace.run_id, "test-sender")
        await bus.publish(req)
        await asyncio.sleep(10.0)
    finally:
        tester.stop()

    # TesterAgent publishes dev.test.failed when exit_code != 0
    assert len(failed_msgs) == 1, "Should have published test-failed"
    assert len(completed) == 0, "Should not have published completed"
