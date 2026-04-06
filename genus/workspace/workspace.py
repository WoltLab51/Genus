"""
Run Workspace Management

Provides the RunWorkspace class for managing per-run isolated workspaces.
Each run gets its own directory structure for repos, artifacts, and logs.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from genus.workspace.paths import (
    default_workspace_root,
    safe_run_id,
    ensure_within,
)


@dataclass
class RunWorkspace:
    """Per-run workspace with isolated directory structure.

    A RunWorkspace provides isolated directories for a single GENUS run,
    preventing interference between concurrent runs and keeping the main
    checkout clean.

    Attributes:
        run_id: The unique run identifier (from genus.core.run.new_run_id).
        root: The root directory for this workspace.

    Directory structure::

        {root}/
        ├── repo/        # Git repository checkout
        ├── artifacts/   # Build outputs, logs, etc.
        └── temp/        # Temporary files

    Example::

        workspace = RunWorkspace.create("2026-04-05T14-07-12Z__task__abc123")
        workspace.ensure_dirs()

        # Use workspace directories
        repo_path = workspace.repo_dir
        artifacts = workspace.artifacts_dir
    """

    run_id: str
    root: Path

    @property
    def repo_dir(self) -> Path:
        """Return the path to the repository checkout directory.

        Returns:
            Path to repo/ subdirectory within the workspace.
        """
        return self.root / "repo"

    @property
    def artifacts_dir(self) -> Path:
        """Return the path to the artifacts directory.

        Returns:
            Path to artifacts/ subdirectory for build outputs, logs, etc.
        """
        return self.root / "artifacts"

    @property
    def temp_dir(self) -> Path:
        """Return the path to the temporary files directory.

        Returns:
            Path to temp/ subdirectory for ephemeral files.
        """
        return self.root / "temp"

    @classmethod
    def create(
        cls,
        run_id: str,
        workspace_root: Optional[Path] = None,
    ) -> "RunWorkspace":
        """Create a new RunWorkspace for the given run_id.

        Args:
            run_id: The unique run identifier (from genus.core.run.new_run_id).
            workspace_root: Optional custom workspace root directory.
                           Defaults to ~/genus-workspaces.

        Returns:
            A new RunWorkspace instance.

        Raises:
            ValueError: If run_id is invalid or unsafe for filesystem use.

        Example::

            workspace = RunWorkspace.create("2026-04-05T14-07-12Z__task__abc123")
        """
        # Sanitize run_id for filesystem safety (especially Windows)
        safe_id = safe_run_id(run_id)

        # Determine workspace root
        if workspace_root is None:
            workspace_root = default_workspace_root()

        # Create workspace root path
        root = workspace_root / safe_id

        return cls(run_id=run_id, root=root)

    def ensure_dirs(self) -> None:
        """Create all workspace directories if they don't exist.

        Creates the workspace root and all standard subdirectories:
        - repo/
        - artifacts/
        - temp/

        This method is idempotent and safe to call multiple times.

        Example::

            workspace = RunWorkspace.create("run123")
            workspace.ensure_dirs()  # Creates all directories
        """
        self.root.mkdir(parents=True, exist_ok=True)
        self.repo_dir.mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)

    def get_safe_path(self, relative_path: str) -> Path:
        """Return a safe absolute path within the workspace.

        Validates that the resulting path is within the workspace root,
        protecting against path traversal attacks.

        Args:
            relative_path: A relative path within the workspace.

        Returns:
            The validated absolute path within the workspace.

        Raises:
            ValueError: If the path would escape the workspace root.

        Example::

            workspace = RunWorkspace.create("run123")
            safe_path = workspace.get_safe_path("repo/src/main.py")
            # Returns: /home/user/genus-workspaces/run123/repo/src/main.py

            # This would raise ValueError:
            # workspace.get_safe_path("../../etc/passwd")
        """
        target = self.root / relative_path
        return ensure_within(self.root, target)
