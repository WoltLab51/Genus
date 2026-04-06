"""
Read-Only Repository Tools

Provides tools for reading and searching repository files without
making any modifications. All tools include evidence capture for
traceability.

Evidence format:
    All tool responses include an "evidence" field containing machine-readable
    references (file paths, line numbers, matched patterns) that allow
    Planner and Reviewer agents to track the reasoning chain.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class Evidence:
    """Machine-readable evidence reference for tool operations.

    Attributes:
        tool: Name of the tool that generated this evidence.
        path: File path (relative to repo root) involved in the operation.
        line_numbers: Optional list of line numbers referenced.
        matched_pattern: Optional search pattern that was matched.
        metadata: Additional tool-specific metadata.
    """

    tool: str
    path: str
    line_numbers: Optional[List[int]] = None
    matched_pattern: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence to a dictionary for serialization."""
        result = {
            "tool": self.tool,
            "path": self.path,
        }
        if self.line_numbers is not None:
            result["line_numbers"] = self.line_numbers
        if self.matched_pattern is not None:
            result["matched_pattern"] = self.matched_pattern
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class ToolResponse:
    """Standard response format for read-only repo tools.

    Attributes:
        success: Whether the operation succeeded.
        data: The main result data (file content, tree listing, search results).
        evidence: Machine-readable evidence references.
        error: Optional error message if success is False.
    """

    success: bool
    data: Any
    evidence: List[Evidence] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to a dictionary for serialization."""
        result = {
            "success": self.success,
            "data": self.data,
            "evidence": [e.to_dict() for e in self.evidence],
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def read_file(repo_dir: Path, file_path: str) -> ToolResponse:
    """Read a file from the repository.

    This is a read-only operation that does not modify the repository.

    Args:
        repo_dir: Root directory of the repository.
        file_path: Path to the file relative to repo_dir.

    Returns:
        ToolResponse with file content and evidence.

    Example::

        response = read_file(Path("/repo"), "src/main.py")
        if response.success:
            print(response.data)  # File content as string
            print(response.evidence)  # [Evidence(tool="read_file", path="src/main.py")]
    """
    try:
        target = repo_dir / file_path
        # Security: Ensure path is within repo_dir
        target_resolved = target.resolve()
        repo_resolved = repo_dir.resolve()

        try:
            target_resolved.relative_to(repo_resolved)
        except ValueError:
            return ToolResponse(
                success=False,
                data=None,
                error="Path '{}' is outside repository directory".format(file_path),
            )

        # Read file content
        if not target_resolved.exists():
            return ToolResponse(
                success=False,
                data=None,
                error="File '{}' not found".format(file_path),
            )

        if not target_resolved.is_file():
            return ToolResponse(
                success=False,
                data=None,
                error="Path '{}' is not a file".format(file_path),
            )

        content = target_resolved.read_text(encoding="utf-8")

        # Create evidence
        evidence = Evidence(
            tool="read_file",
            path=file_path,
            metadata={"size_bytes": len(content.encode("utf-8"))},
        )

        return ToolResponse(
            success=True,
            data=content,
            evidence=[evidence],
        )

    except UnicodeDecodeError as e:
        return ToolResponse(
            success=False,
            data=None,
            error="File '{}' is not a valid UTF-8 text file: {}".format(file_path, str(e)),
        )
    except Exception as e:
        return ToolResponse(
            success=False,
            data=None,
            error="Error reading file '{}': {}".format(file_path, str(e)),
        )


def list_tree(
    repo_dir: Path,
    sub_path: str = ".",
    max_depth: Optional[int] = None,
    include_pattern: Optional[str] = None,
) -> ToolResponse:
    """List directory tree structure in the repository.

    This is a read-only operation that does not modify the repository.

    Args:
        repo_dir: Root directory of the repository.
        sub_path: Subdirectory to list (relative to repo_dir). Defaults to ".".
        max_depth: Maximum depth to traverse. None means unlimited.
        include_pattern: Optional regex pattern to filter files/directories.

    Returns:
        ToolResponse with list of relative paths and evidence.

    Example::

        response = list_tree(Path("/repo"), "src", max_depth=2)
        if response.success:
            for path in response.data:
                print(path)  # e.g., "src/main.py", "src/utils/helper.py"
    """
    try:
        target = repo_dir / sub_path
        # Security: Ensure path is within repo_dir
        target_resolved = target.resolve()
        repo_resolved = repo_dir.resolve()

        try:
            target_resolved.relative_to(repo_resolved)
        except ValueError:
            return ToolResponse(
                success=False,
                data=None,
                error="Path '{}' is outside repository directory".format(sub_path),
            )

        if not target_resolved.exists():
            return ToolResponse(
                success=False,
                data=None,
                error="Path '{}' not found".format(sub_path),
            )

        if not target_resolved.is_dir():
            return ToolResponse(
                success=False,
                data=None,
                error="Path '{}' is not a directory".format(sub_path),
            )

        # Compile pattern if provided
        pattern = re.compile(include_pattern) if include_pattern else None

        # Walk directory tree
        paths = []
        for item in _walk_directory(target_resolved, repo_resolved, max_depth, pattern):
            paths.append(item)

        # Create evidence
        evidence = Evidence(
            tool="list_tree",
            path=sub_path,
            metadata={
                "file_count": len(paths),
                "max_depth": max_depth,
                "include_pattern": include_pattern,
            },
        )

        return ToolResponse(
            success=True,
            data=sorted(paths),
            evidence=[evidence],
        )

    except Exception as e:
        return ToolResponse(
            success=False,
            data=None,
            error="Error listing directory '{}': {}".format(sub_path, str(e)),
        )


def _walk_directory(
    start: Path,
    repo_root: Path,
    max_depth: Optional[int],
    pattern: Optional[re.Pattern],
    current_depth: int = 0,
) -> List[str]:
    """Recursively walk directory tree and collect relative paths.

    Args:
        start: Starting directory.
        repo_root: Repository root for computing relative paths.
        max_depth: Maximum depth to traverse.
        pattern: Optional regex pattern to filter paths.
        current_depth: Current recursion depth.

    Returns:
        List of relative paths from repo_root.
    """
    results = []

    if max_depth is not None and current_depth >= max_depth:
        return results

    try:
        for item in sorted(start.iterdir()):
            rel_path = str(item.relative_to(repo_root))

            # Apply pattern filter
            if pattern and not pattern.search(rel_path):
                continue

            results.append(rel_path)

            # Recurse into subdirectories
            if item.is_dir():
                results.extend(
                    _walk_directory(item, repo_root, max_depth, pattern, current_depth + 1)
                )

    except PermissionError:
        # Skip directories we can't read
        pass

    return results


@dataclass
class GrepMatch:
    """A single grep match result.

    Attributes:
        file_path: Path to the file (relative to repo root).
        line_number: Line number (1-indexed).
        line_content: Content of the matched line.
        match_start: Start position of match in line (0-indexed).
        match_end: End position of match in line (0-indexed).
    """

    file_path: str
    line_number: int
    line_content: str
    match_start: int
    match_end: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert match to a dictionary for serialization."""
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_content": self.line_content,
            "match_start": self.match_start,
            "match_end": self.match_end,
        }


def grep_text(
    repo_dir: Path,
    pattern: str,
    file_pattern: Optional[str] = None,
    max_matches: int = 100,
) -> ToolResponse:
    r"""Search for text pattern in repository files.

    This is a read-only operation that does not modify the repository.

    Args:
        repo_dir: Root directory of the repository.
        pattern: Regex pattern to search for.
        file_pattern: Optional regex to filter which files to search.
        max_matches: Maximum number of matches to return (default 100).

    Returns:
        ToolResponse with list of GrepMatch objects and evidence.

    Example::

        response = grep_text(Path("/repo"), r"def.*test", file_pattern=r".*\.py$")
        if response.success:
            for match in response.data:
                print(f"{match.file_path}:{match.line_number}: {match.line_content}")
    """
    try:
        # Compile patterns
        search_pattern = re.compile(pattern)
        file_filter = re.compile(file_pattern) if file_pattern else None

        matches = []
        repo_resolved = repo_dir.resolve()

        # Walk all files in repo
        for file_path in repo_resolved.rglob("*"):
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(repo_resolved))

            # Apply file filter
            if file_filter and not file_filter.search(rel_path):
                continue

            # Search file content
            try:
                content = file_path.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.splitlines(), start=1):
                    match = search_pattern.search(line)
                    if match:
                        matches.append(
                            GrepMatch(
                                file_path=rel_path,
                                line_number=line_num,
                                line_content=line.rstrip(),
                                match_start=match.start(),
                                match_end=match.end(),
                            )
                        )

                        # Respect max_matches limit
                        if len(matches) >= max_matches:
                            break

            except (UnicodeDecodeError, PermissionError):
                # Skip binary files or files we can't read
                continue

            if len(matches) >= max_matches:
                break

        # Create evidence for all matched files
        evidence_list = []
        file_groups = {}
        for match in matches:
            if match.file_path not in file_groups:
                file_groups[match.file_path] = []
            file_groups[match.file_path].append(match.line_number)

        for file_path, line_numbers in file_groups.items():
            evidence_list.append(
                Evidence(
                    tool="grep_text",
                    path=file_path,
                    line_numbers=line_numbers,
                    matched_pattern=pattern,
                )
            )

        # Convert matches to dicts for data field
        match_dicts = [m.to_dict() for m in matches]

        return ToolResponse(
            success=True,
            data=match_dicts,
            evidence=evidence_list,
        )

    except re.error as e:
        return ToolResponse(
            success=False,
            data=None,
            error="Invalid regex pattern '{}': {}".format(pattern, str(e)),
        )
    except Exception as e:
        return ToolResponse(
            success=False,
            data=None,
            error="Error searching repository: {}".format(str(e)),
        )
