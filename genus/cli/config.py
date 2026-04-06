"""
CLI Configuration Module

Provides configuration dataclass for GENUS CLI operations.
Uses dataclass for compatibility with Python 3.8+.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CliConfig:
    """Configuration for GENUS CLI operations.

    Attributes:
        workspace_root: Root directory for all GENUS workspaces.
                       Defaults to ~/genus-workspaces
        runs_store_dir: Directory for storing run journals.
                       Defaults to workspace_root/var/runs
        github_owner: Optional GitHub repository owner (e.g., "WoltLab51").
        github_repo: Optional GitHub repository name (e.g., "Genus").
        github_base_branch: Optional base branch for PRs (default "main").
        push_enabled: Whether to allow git push operations (default False).
        pr_creation_enabled: Whether to allow PR creation (default False).
    """

    workspace_root: Path = field(
        default_factory=lambda: Path.home() / "genus-workspaces"
    )
    runs_store_dir: Optional[Path] = None
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None
    github_base_branch: str = "main"
    push_enabled: bool = False
    pr_creation_enabled: bool = False

    def __post_init__(self):
        """Initialize derived paths and validate configuration."""
        # Convert workspace_root to Path if it's a string
        if isinstance(self.workspace_root, str):
            self.workspace_root = Path(self.workspace_root)

        # Default runs_store_dir to workspace_root/var/runs
        if self.runs_store_dir is None:
            self.runs_store_dir = self.workspace_root / "var" / "runs"
        elif isinstance(self.runs_store_dir, str):
            self.runs_store_dir = Path(self.runs_store_dir)

    def get_runs_store_dir(self) -> Path:
        """Get the runs store directory path.

        Returns:
            Path to the runs store directory.
        """
        return self.runs_store_dir or self.workspace_root / "var" / "runs"
