# Workspace Module

The `genus.workspace` module provides per-run workspace isolation with Windows-safe path handling and read-only repository tools with evidence capture.

## Overview

GENUS runs need isolated workspaces to:
- Prevent interference between concurrent runs
- Keep the main repository checkout clean
- Provide safe directory structures for build artifacts and temporary files
- Enable Windows compatibility with filesystem-safe path normalization

## Key Components

### 1. Path Utilities (`genus.workspace.paths`)

Windows-safe path normalization and validation functions.

#### `default_workspace_root() -> Path`

Returns the default workspace root directory (`~/genus-workspaces`).

```python
from genus.workspace import default_workspace_root

root = default_workspace_root()
# Returns: Path('/home/user/genus-workspaces')
```

#### `safe_run_id(run_id: str) -> str`

Sanitizes a run ID for filesystem safety, especially on Windows.

- Replaces problematic characters (`:`, `\`, `/`, `<`, `>`, `|`, `?`, `*`) with underscores
- Only allows `[a-zA-Z0-9._-]` characters
- Removes path traversal patterns (`..`)
- Guarantees non-empty result

```python
from genus.workspace import safe_run_id

# Timestamp contains colons (Windows-problematic)
run_id = "2026-04-05T14:07:12Z__task__abc123"
safe = safe_run_id(run_id)
# Returns: "2026-04-05T14_07_12Z__task__abc123"
```

#### `ensure_within(base: Path, target: Path) -> Path`

Validates that a target path is within a base directory, protecting against path traversal attacks.

```python
from pathlib import Path
from genus.workspace import ensure_within

base = Path("/workspace")
target = Path("/workspace/subdir/file.txt")
safe_path = ensure_within(base, target)  # OK

# This would raise ValueError:
# ensure_within(base, Path("/workspace/../etc/passwd"))
```

### 2. Run Workspace (`genus.workspace.workspace`)

#### `RunWorkspace`

A dataclass that manages per-run isolated directory structures.

**Directory Structure:**
```
{workspace_root}/{run_id}/
├── repo/        # Git repository checkout
├── artifacts/   # Build outputs, logs, etc.
└── temp/        # Temporary files
```

**Usage:**

```python
from genus.workspace import RunWorkspace

# Create workspace for a run
workspace = RunWorkspace.create("2026-04-05T14-07-12Z__task__abc123")

# Create all directories
workspace.ensure_dirs()

# Access directory paths
repo_path = workspace.repo_dir
artifacts_path = workspace.artifacts_dir
temp_path = workspace.temp_dir

# Safely resolve paths within workspace
safe_file = workspace.get_safe_path("repo/src/main.py")
```

**Properties:**
- `repo_dir: Path` - Repository checkout directory
- `artifacts_dir: Path` - Artifacts directory for build outputs
- `temp_dir: Path` - Temporary files directory

**Methods:**
- `create(run_id, workspace_root=None)` - Factory method to create a workspace
- `ensure_dirs()` - Create all workspace directories (idempotent)
- `get_safe_path(relative_path)` - Validate and resolve paths within workspace

### 3. Read-Only Repository Tools (`genus.workspace.repo_tools`)

Tools for reading and searching repository files without making modifications. All tools include evidence capture for traceability.

#### Evidence Capture

All tool responses include machine-readable evidence references:

```python
from genus.workspace import Evidence

evidence = Evidence(
    tool="read_file",
    path="src/main.py",
    line_numbers=[10, 25, 42],  # Optional
    matched_pattern=r"def.*",   # Optional
    metadata={"size_bytes": 1024}  # Optional
)
```

#### `read_file(repo_dir: Path, file_path: str) -> ToolResponse`

Read a file from the repository.

```python
from pathlib import Path
from genus.workspace import read_file

response = read_file(Path("/repo"), "src/main.py")
if response.success:
    print(response.data)  # File content
    print(response.evidence[0].path)  # "src/main.py"
else:
    print(response.error)
```

**Features:**
- UTF-8 text file reading
- Path traversal protection
- Size metadata in evidence
- Error handling for binary files

#### `list_tree(repo_dir: Path, sub_path=".", max_depth=None, include_pattern=None) -> ToolResponse`

List directory tree structure.

```python
from genus.workspace import list_tree

# List all files in src/ directory, max depth 2
response = list_tree(
    Path("/repo"),
    sub_path="src",
    max_depth=2,
    include_pattern=r"\.py$"  # Only Python files
)

if response.success:
    for path in response.data:
        print(path)  # Relative paths from repo root
```

**Features:**
- Recursive directory traversal
- Depth limiting
- Regex pattern filtering
- Sorted output

#### `grep_text(repo_dir: Path, pattern: str, file_pattern=None, max_matches=100) -> ToolResponse`

Search for text patterns in repository files.

```python
from genus.workspace import grep_text

# Find all function definitions in Python files
response = grep_text(
    Path("/repo"),
    pattern=r"def\s+\w+",
    file_pattern=r"\.py$",
    max_matches=50
)

if response.success:
    for match in response.data:
        print(f"{match['file_path']}:{match['line_number']}: {match['line_content']}")
```

**Features:**
- Regex pattern search
- File pattern filtering
- Match position tracking (start/end indices)
- Line number references
- Automatic binary file skipping
- Evidence includes all matched files and line numbers

#### Tool Response Format

All tools return a `ToolResponse` object:

```python
@dataclass
class ToolResponse:
    success: bool           # Whether operation succeeded
    data: Any              # Main result data
    evidence: List[Evidence]  # Machine-readable evidence
    error: Optional[str]    # Error message if failed
```

## Security Features

1. **Path Traversal Protection**: All tools validate paths using `ensure_within()` to prevent `..` attacks
2. **Windows Compatibility**: `safe_run_id()` sanitizes paths for Windows filesystems
3. **Read-Only Operations**: No tools modify the repository
4. **UTF-8 Validation**: Binary files are detected and rejected appropriately

## Integration with GENUS Core

The workspace module integrates with `genus.core.run` for run ID management:

```python
from genus.core.run import new_run_id
from genus.workspace import RunWorkspace

# Generate a new run ID
run_id = new_run_id(slug="code-review")
# Returns: "2026-04-06T14-30-00Z__code-review__x7k2m9"

# Create workspace for this run
workspace = RunWorkspace.create(run_id)
workspace.ensure_dirs()

# Now the workspace is ready for the run
print(f"Workspace: {workspace.root}")
print(f"Repository: {workspace.repo_dir}")
```

## Example: Complete Workflow

```python
from pathlib import Path
from genus.core.run import new_run_id
from genus.workspace import (
    RunWorkspace,
    read_file,
    list_tree,
    grep_text,
)

# 1. Create workspace
run_id = new_run_id(slug="analyze-codebase")
workspace = RunWorkspace.create(run_id)
workspace.ensure_dirs()

# 2. (Assume repository is cloned to workspace.repo_dir)

# 3. List Python files
tree_response = list_tree(
    workspace.repo_dir,
    sub_path="src",
    include_pattern=r"\.py$"
)

# 4. Search for TODO comments
grep_response = grep_text(
    workspace.repo_dir,
    pattern=r"TODO:.*",
    file_pattern=r"\.py$"
)

# 5. Read specific file
file_response = read_file(workspace.repo_dir, "src/main.py")

# 6. Process evidence for tracking
all_evidence = (
    tree_response.evidence +
    grep_response.evidence +
    file_response.evidence
)

for ev in all_evidence:
    print(f"Tool: {ev.tool}, Path: {ev.path}")
```

## Testing

The workspace module includes comprehensive unit tests:

- `tests/unit/test_workspace_paths.py` - Path utility tests (19 tests)
- `tests/unit/test_workspace.py` - RunWorkspace tests (16 tests)
- `tests/unit/test_workspace_repo_tools.py` - Tool tests (33 tests)

Run tests with:
```bash
pytest tests/unit/test_workspace*.py -v
```

## Design Principles

1. **Isolation**: Each run gets its own workspace directory
2. **Safety**: Path validation prevents traversal attacks
3. **Traceability**: Evidence capture enables audit trails
4. **Cross-platform**: Windows-safe path handling
5. **Read-only**: No repository modifications
6. **Explicit**: No hidden side effects or global state
