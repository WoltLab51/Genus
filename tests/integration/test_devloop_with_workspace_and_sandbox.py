"""
Integration test: DevLoop with Workspace and Sandbox (PR #28)

Tests the end-to-end dev loop with real workspace operations:
- BuilderAgent writes files and commits
- TesterAgent runs tests in sandbox
- Orchestrator coordinates the flow
"""

import pytest
import asyncio
from pathlib import Path
from genus.communication.message_bus import MessageBus
from genus.core.run import new_run_id
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.dev.agents.planner_agent import PlannerAgent
from genus.dev.agents.builder_agent import BuilderAgent
from genus.dev.agents.tester_agent import TesterAgent


@pytest.mark.asyncio
async def test_devloop_with_workspace_and_sandbox(tmp_path):
    """Test complete dev loop with workspace operations and sandbox execution.

    This is a minimal end-to-end test for PR #28:
    1. Setup workspace with minimal git repo
    2. Start agents with workspace + allowlist
    3. Run orchestrator
    4. Assert: implement completed, test completed, loop completed
    """
    # Setup workspace
    run_id = new_run_id()
    workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)
    workspace.ensure_dirs()

    # Create minimal git repo in workspace.repo_dir
    repo_dir = workspace.repo_dir
    _setup_minimal_git_repo(repo_dir)

    # Create journal
    store = JsonlRunStore(base_dir=tmp_path / "runs")
    journal = RunJournal(run_id, store)
    journal.initialize(goal="Test workspace and sandbox integration")

    # Create message bus
    bus = MessageBus()

    # Create agents with workspace integration
    planner = PlannerAgent(bus, agent_id="planner")
    builder = BuilderAgent(
        bus,
        agent_id="builder",
        workspace=workspace,
        branch_name=None,  # Don't create branch in test (already on main)
        allowed_write_paths=["docs/", "tests/"],
        journal=journal,
    )
    tester = TesterAgent(
        bus,
        agent_id="tester",
        workspace=workspace,
        test_argv=["python", "-m", "pytest", "-q", "tests/"],
        journal=journal,
    )

    # Create orchestrator
    orchestrator = DevLoopOrchestrator(
        bus=bus,
        run_id=run_id,
        goal="Write a test file and verify it passes",
        max_iterations=1,
    )

    # Start agents
    planner.start()
    builder.start()
    tester.start()

    try:
        # Run orchestrator (should complete one loop iteration)
        result = await asyncio.wait_for(orchestrator.run(), timeout=30.0)

        # Assert loop completed successfully
        assert result["status"] == "completed", f"Expected completed, got {result['status']}"
        assert result["iterations"] >= 1, "Should have completed at least 1 iteration"

        # Verify files were created/modified in workspace
        devloop_note = repo_dir / "docs" / "DEVLOOP_NOTE.md"
        assert devloop_note.exists(), "BuilderAgent should have created DEVLOOP_NOTE.md"

        # Verify git commit was made
        import subprocess

        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
        )
        assert git_log.returncode == 0
        assert "GENUS" in git_log.stdout or "feat:" in git_log.stdout

        # Verify journal has events
        events = journal.get_events()
        assert len(events) > 0, "Journal should have recorded events"

        # Check for tool usage events
        tool_events = journal.get_events(event_type="tool_used")
        assert len(tool_events) > 0, "Should have logged tool usage"

    finally:
        # Stop agents
        planner.stop()
        builder.stop()
        tester.stop()


@pytest.mark.asyncio
async def test_builder_with_workspace_creates_file(tmp_path):
    """Test BuilderAgent creates file and commits when workspace is provided."""
    run_id = new_run_id()
    workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)
    workspace.ensure_dirs()

    # Setup git repo
    repo_dir = workspace.repo_dir
    _setup_minimal_git_repo(repo_dir)

    # Create bus and agent
    bus = MessageBus()
    builder = BuilderAgent(
        bus,
        agent_id="builder",
        workspace=workspace,
        allowed_write_paths=["docs/"],
    )

    # Track messages
    completed_messages = []

    def track_completed(msg):
        completed_messages.append(msg)

    bus.subscribe("dev.implement.completed", track_completed, "tracker")
    builder.start()

    try:
        # Publish implement request
        from genus.dev import events

        request = events.dev_implement_requested_message(
            run_id=run_id,
            sender_id="test",
            plan={"steps": ["Create a note file"]},
        )

        await bus.publish(request)

        # Wait for completion
        await asyncio.sleep(2.0)

        # Assert file was created
        devloop_note = repo_dir / "docs" / "DEVLOOP_NOTE.md"
        assert devloop_note.exists()

        # Assert commit was made
        import subprocess

        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
        )
        assert git_log.returncode == 0
        assert len(git_log.stdout) > 0

        # Assert completion message was published
        assert len(completed_messages) == 1

    finally:
        builder.stop()


@pytest.mark.asyncio
async def test_tester_with_workspace_runs_real_tests(tmp_path):
    """Test TesterAgent runs pytest in sandbox when workspace is provided."""
    run_id = new_run_id()
    workspace = RunWorkspace.create(run_id, workspace_root=tmp_path)
    workspace.ensure_dirs()

    # Setup git repo with a passing test
    repo_dir = workspace.repo_dir
    _setup_minimal_git_repo(repo_dir)

    # Create a simple passing test
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_simple.py").write_text(
        "def test_always_passes():\n    assert True\n"
    )

    # Create bus and agent
    bus = MessageBus()
    tester = TesterAgent(
        bus,
        agent_id="tester",
        workspace=workspace,
        test_argv=["python", "-m", "pytest", "-q", "tests/"],
    )

    # Track messages
    completed_messages = []

    def track_completed(msg):
        completed_messages.append(msg)

    bus.subscribe("dev.test.completed", track_completed, "tracker")
    tester.start()

    try:
        # Publish test request
        from genus.dev import events

        request = events.dev_test_requested_message(
            run_id=run_id,
            sender_id="test",
        )

        await bus.publish(request)

        # Wait for completion
        await asyncio.sleep(5.0)

        # Assert completion message was published
        assert len(completed_messages) == 1
        report = completed_messages[0].payload["report"]
        assert report["exit_code"] == 0
        assert not report["timed_out"]

    finally:
        tester.stop()


def _setup_minimal_git_repo(repo_dir: Path):
    """Create a minimal git repo in the given directory.

    Args:
        repo_dir: Directory to initialize as git repo.
    """
    import subprocess

    # Init repo
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True)

    # Configure git (required for commits)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo_dir),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo_dir),
        check=True,
    )

    # Create initial structure
    (repo_dir / "docs").mkdir(exist_ok=True)
    (repo_dir / "tests").mkdir(exist_ok=True)
    (repo_dir / "README.md").write_text("# Test Repo\n")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=str(repo_dir), check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(repo_dir),
        check=True,
    )
