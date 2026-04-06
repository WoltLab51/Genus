"""
Unit tests for CLI argument parsing.
"""

import pytest
from pathlib import Path
from genus.cli.main import parse_args


def test_parse_args_run_command():
    """Test parsing the run command."""
    args = parse_args(["run", "--goal", "Test goal"])

    assert args.command == "run"
    assert args.goal == "Test goal"
    assert args.requirements is None
    assert args.constraints is None


def test_parse_args_run_with_requirements():
    """Test parsing run command with requirements."""
    args = parse_args([
        "run",
        "--goal", "Test goal",
        "--requirements", "req1", "req2", "req3",
    ])

    assert args.goal == "Test goal"
    assert args.requirements == ["req1", "req2", "req3"]


def test_parse_args_run_with_constraints():
    """Test parsing run command with constraints."""
    args = parse_args([
        "run",
        "--goal", "Test goal",
        "--constraints", "no network", "Python 3.8+",
    ])

    assert args.constraints == ["no network", "Python 3.8+"]


def test_parse_args_run_with_github_config():
    """Test parsing run command with GitHub configuration."""
    args = parse_args([
        "run",
        "--goal", "Test goal",
        "--github-owner", "TestOwner",
        "--github-repo", "TestRepo",
        "--github-base-branch", "develop",
    ])

    assert args.github_owner == "TestOwner"
    assert args.github_repo == "TestRepo"
    assert args.github_base_branch == "develop"


def test_parse_args_run_with_branch():
    """Test parsing run command with branch."""
    args = parse_args([
        "run",
        "--goal", "Test goal",
        "--branch", "feature/test",
    ])

    assert args.branch == "feature/test"


def test_parse_args_run_with_workspace():
    """Test parsing run command with custom workspace."""
    args = parse_args([
        "--workspace-root", "/tmp/workspaces",
        "run",
        "--goal", "Test goal",
    ])

    assert args.workspace_root == Path("/tmp/workspaces")


def test_parse_args_resume_command():
    """Test parsing the resume command."""
    args = parse_args([
        "resume",
        "--run-id", "2026-04-06T12-00-00Z__test__abc123",
    ])

    assert args.command == "resume"
    assert args.run_id == "2026-04-06T12-00-00Z__test__abc123"
    assert args.force is False


def test_parse_args_resume_with_force():
    """Test parsing resume command with force flag."""
    args = parse_args([
        "resume",
        "--run-id", "test-run-id",
        "--force",
    ])

    assert args.force is True


def test_parse_args_report_command():
    """Test parsing the report command."""
    args = parse_args([
        "report",
        "--run-id", "2026-04-06T12-00-00Z__test__abc123",
    ])

    assert args.command == "report"
    assert args.run_id == "2026-04-06T12-00-00Z__test__abc123"
    assert args.format == "text"
    assert args.output is None


def test_parse_args_report_with_format():
    """Test parsing report command with format."""
    args = parse_args([
        "report",
        "--run-id", "test-run-id",
        "--format", "md",
    ])

    assert args.format == "md"


def test_parse_args_report_with_output():
    """Test parsing report command with output file."""
    args = parse_args([
        "report",
        "--run-id", "test-run-id",
        "--output", "/tmp/report.txt",
    ])

    assert args.output == Path("/tmp/report.txt")


def test_parse_args_no_command():
    """Test parsing with no command."""
    args = parse_args([])

    assert args.command is None


def test_parse_args_global_runs_store_dir():
    """Test parsing with global runs-store-dir option."""
    args = parse_args([
        "--runs-store-dir", "/var/genus/runs",
        "run",
        "--goal", "Test",
    ])

    assert args.runs_store_dir == Path("/var/genus/runs")


def test_parse_args_run_all_options():
    """Test parsing run command with all options."""
    args = parse_args([
        "--workspace-root", "/tmp/workspaces",
        "--runs-store-dir", "/tmp/runs",
        "run",
        "--goal", "Complex goal",
        "--requirements", "req1", "req2",
        "--constraints", "const1",
        "--branch", "feature/test",
        "--github-owner", "Owner",
        "--github-repo", "Repo",
        "--github-base-branch", "develop",
    ])

    assert args.command == "run"
    assert args.workspace_root == Path("/tmp/workspaces")
    assert args.runs_store_dir == Path("/tmp/runs")
    assert args.goal == "Complex goal"
    assert args.requirements == ["req1", "req2"]
    assert args.constraints == ["const1"]
    assert args.branch == "feature/test"
    assert args.github_owner == "Owner"
    assert args.github_repo == "Repo"
    assert args.github_base_branch == "develop"


def test_parse_args_list_runs_command():
    """Test parsing the list-runs command."""
    args = parse_args(["list-runs"])

    assert args.command == "list-runs"
    assert args.limit == 20
    assert args.format == "text"


def test_parse_args_list_runs_with_limit():
    """Test parsing list-runs command with custom limit."""
    args = parse_args(["list-runs", "--limit", "50"])

    assert args.limit == 50


def test_parse_args_list_runs_with_format():
    """Test parsing list-runs command with markdown format."""
    args = parse_args(["list-runs", "--format", "md"])

    assert args.format == "md"


def test_parse_args_list_runs_all_options():
    """Test parsing list-runs command with all options."""
    args = parse_args([
        "--runs-store-dir", "/custom/runs",
        "list-runs",
        "--limit", "100",
        "--format", "md",
    ])

    assert args.command == "list-runs"
    assert args.runs_store_dir == Path("/custom/runs")
    assert args.limit == 100
    assert args.format == "md"

