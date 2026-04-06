"""
Unit tests for CLI configuration.
"""

import pytest
from pathlib import Path
from genus.cli.config import CliConfig


def test_cli_config_defaults():
    """Test CliConfig with default values."""
    config = CliConfig()

    assert config.workspace_root == Path.home() / "genus-workspaces"
    assert config.runs_store_dir == Path.home() / "genus-workspaces" / "var" / "runs"
    assert config.github_owner is None
    assert config.github_repo is None
    assert config.github_base_branch == "main"
    assert config.push_enabled is False
    assert config.pr_creation_enabled is False


def test_cli_config_custom_workspace():
    """Test CliConfig with custom workspace root."""
    config = CliConfig(workspace_root=Path("/tmp/workspaces"))

    assert config.workspace_root == Path("/tmp/workspaces")
    assert config.runs_store_dir == Path("/tmp/workspaces") / "var" / "runs"


def test_cli_config_custom_runs_store():
    """Test CliConfig with custom runs store directory."""
    config = CliConfig(
        workspace_root=Path("/tmp/workspaces"),
        runs_store_dir=Path("/var/genus/runs"),
    )

    assert config.runs_store_dir == Path("/var/genus/runs")


def test_cli_config_string_paths():
    """Test CliConfig with string paths (converted to Path)."""
    config = CliConfig(
        workspace_root="/tmp/workspaces",
        runs_store_dir="/var/runs",
    )

    assert isinstance(config.workspace_root, Path)
    assert config.workspace_root == Path("/tmp/workspaces")
    assert isinstance(config.runs_store_dir, Path)
    assert config.runs_store_dir == Path("/var/runs")


def test_cli_config_github_settings():
    """Test CliConfig with GitHub settings."""
    config = CliConfig(
        github_owner="TestOwner",
        github_repo="TestRepo",
        github_base_branch="develop",
    )

    assert config.github_owner == "TestOwner"
    assert config.github_repo == "TestRepo"
    assert config.github_base_branch == "develop"


def test_cli_config_enable_push():
    """Test CliConfig with push enabled."""
    config = CliConfig(push_enabled=True)

    assert config.push_enabled is True


def test_cli_config_enable_pr_creation():
    """Test CliConfig with PR creation enabled."""
    config = CliConfig(pr_creation_enabled=True)

    assert config.pr_creation_enabled is True


def test_cli_config_get_runs_store_dir():
    """Test get_runs_store_dir method."""
    config = CliConfig(workspace_root=Path("/tmp/workspaces"))

    runs_dir = config.get_runs_store_dir()

    assert runs_dir == Path("/tmp/workspaces") / "var" / "runs"


def test_cli_config_get_runs_store_dir_custom():
    """Test get_runs_store_dir with custom runs store."""
    config = CliConfig(runs_store_dir=Path("/custom/runs"))

    runs_dir = config.get_runs_store_dir()

    assert runs_dir == Path("/custom/runs")


def test_cli_config_all_settings():
    """Test CliConfig with all settings configured."""
    config = CliConfig(
        workspace_root=Path("/tmp/workspaces"),
        runs_store_dir=Path("/var/runs"),
        github_owner="Owner",
        github_repo="Repo",
        github_base_branch="develop",
        push_enabled=True,
        pr_creation_enabled=True,
    )

    assert config.workspace_root == Path("/tmp/workspaces")
    assert config.runs_store_dir == Path("/var/runs")
    assert config.github_owner == "Owner"
    assert config.github_repo == "Repo"
    assert config.github_base_branch == "develop"
    assert config.push_enabled is True
    assert config.pr_creation_enabled is True
