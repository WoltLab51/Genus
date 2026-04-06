# GitHub Automation

This document describes GENUS's GitHub automation capabilities for push, PR creation/update, commenting, and CI checks polling.

## Overview

GENUS can automate GitHub operations while maintaining strict security controls:

- **Branch push**: Push commits to GitHub remotes
- **PR creation/update**: Create new PRs or update existing ones
- **PR commenting**: Add comments to pull requests
- **CI checks polling**: Wait for and monitor GitHub Actions/CI checks

All operations follow GENUS security principles:
- Deny-by-default policy enforcement
- Kill-switch integration
- Memory journal logging
- Ask/Stop gates for sensitive operations
- No auto-merge (only PR operations, never automatic merging)

## Architecture

The GitHub automation system consists of four layers:

1. **Authentication & Configuration** (`genus/github/`)
   - `auth.py`: Secure token retrieval from environment
   - `config.py`: Repository and API configuration

2. **Security Layer** (`genus/security/github_policy.py`)
   - `GitHubPolicy`: Deny-by-default permissions
   - `should_ask_for_github_write()`: Ask/Stop gate logic

3. **API Client** (`genus/github/client.py`)
   - `GitHubClient`: Minimal REST API wrapper
   - Uses Python's built-in `urllib` (no external dependencies)

4. **Tools Layer** (`genus/tools/github_pr.py`)
   - High-level functions for orchestrators
   - Journal integration
   - Policy enforcement

5. **Orchestrator Hook** (`genus/dev/pr_publisher.py`)
   - `publish_run_as_pr()`: Complete PR publishing workflow
   - Keeps GitHub operations separate from core DevLoop

## Required Setup

### 1. Environment Variables

Set a GitHub personal access token:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

**Important**: Never commit tokens to source code or logs.

### 2. Required Permissions/Scopes

Your GitHub token must have these scopes:

- `repo` - Full control of private repositories
  - Includes: read, write, push, PR operations
- `workflow` - Update GitHub Action workflows (if modifying .github/)

To create a token:
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token
3. Select required scopes
4. Copy token and set `GITHUB_TOKEN` environment variable

### 3. Policy Configuration

By default, all write operations are **denied**. Enable them explicitly:

```python
from genus.security.github_policy import GitHubPolicy

# Create permissive policy (for testing/development)
policy = GitHubPolicy(
    allow_push=True,
    allow_create_pr=True,
    allow_comment=True,
    allowed_owner_repos={"WoltLab51/Genus"},  # Allowlist repos
    require_ask_stop_for_push=True,  # Ask before push
    require_ask_stop_for_create_pr=True,  # Ask before PR creation
)
```

**Production defaults** (secure):
```python
# Default policy (all operations denied)
policy = GitHubPolicy()

# Assertions will raise GitHubPolicyError:
policy.assert_action_allowed("push")  # ❌ Raises error
policy.assert_repo_allowed("other", "repo")  # ❌ Raises error
```

## Usage Examples

### Example 1: Simple PR Publishing

```python
from genus.dev.pr_publisher import publish_run_as_pr
from genus.github.config import GitHubConfig
from genus.security.github_policy import GitHubPolicy
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

# Setup
workspace = RunWorkspace.create("my-run-001")
workspace.ensure_dirs()

store = JsonlRunStore()
journal = RunJournal("my-run-001", store)
journal.initialize(goal="Implement new feature")

config = GitHubConfig(
    owner="WoltLab51",
    repo="Genus",
    base_branch="main",
)

policy = GitHubPolicy(
    allow_push=True,
    allow_create_pr=True,
)

# Publish run as PR
result = await publish_run_as_pr(
    run_id="my-run-001",
    workspace=workspace,
    github_config=config,
    policy=policy,
    journal=journal,
    title="feat: add new feature",
    body="This PR adds XYZ feature.\n\nCloses #123",
    branch="feature/my-feature",
    tests_passed=True,
)

if result.success:
    print(f"✓ PR {result.action}: {result.pr_url}")
else:
    print(f"✗ Error: {result.error}")
```

### Example 2: Manual Tool Usage

For more control, use individual tools:

```python
from genus.tools.github_pr import (
    github_push_branch,
    github_create_or_update_pr,
    github_comment_pr,
    github_wait_for_checks,
)
from genus.github.client import GitHubClient
from genus.github.auth import get_github_token_from_env

# Get token
token = get_github_token_from_env()
client = GitHubClient(token, config)

# Push branch
push_result = await github_push_branch(
    workspace=workspace,
    remote="origin",
    branch="feature/test",
    policy=policy,
    journal=journal,
)

# Create or update PR
pr_result = await github_create_or_update_pr(
    workspace=workspace,
    client=client,
    config=config,
    head="feature/test",
    base="main",
    title="Test PR",
    body="Test body",
    policy=policy,
    journal=journal,
)

# Add comment
if pr_result.success:
    comment_result = await github_comment_pr(
        client=client,
        config=config,
        pr_number=pr_result.data["number"],
        comment="✓ All tests passed!",
        policy=policy,
        journal=journal,
    )

# Wait for CI checks
checks_result = await github_wait_for_checks(
    client=client,
    config=config,
    ref="feature/test",
    timeout_s=600,
    journal=journal,
)

if checks_result.data["conclusion"] == "success":
    print("✓ All CI checks passed")
```

### Example 3: Ask/Stop Gate Integration

The `should_ask_for_github_write()` function determines if confirmation is needed:

```python
from genus.security.github_policy import should_ask_for_github_write

should_ask, reason = should_ask_for_github_write(
    action="push",
    branch="main",
    files_changed=50,
    tests_passed=False,
    risk_flags=["large_diff", "security_file_modified"],
)

if should_ask:
    print(f"⚠ Confirmation required: {reason}")
    # In v1, this returns True for all operations (conservative)
    # Future versions can implement more sophisticated logic
```

## Safety Defaults

GENUS prioritizes safety over convenience:

### Default Behavior (v1)

- ✅ All write operations **denied by default**
- ✅ Ask/Stop gates **enabled by default**
- ✅ Only `WoltLab51/Genus` repo allowed by default
- ✅ PR body limited to 20,000 characters
- ✅ No secrets logged to journal
- ✅ No auto-merge functionality

### What You Cannot Do (By Design)

1. **Auto-merge PRs**: GENUS can create/update/comment, but never automatically merge
2. **Bypass policy**: All operations enforce GitHubPolicy
3. **Push without confirmation**: Ask/Stop gate required by default
4. **Access arbitrary repos**: Must be in `allowed_owner_repos` allowlist
5. **Log secrets**: Tokens never appear in journal or logs

### Enabling Operations Intentionally

To enable operations, you must:

1. Create a policy with explicit permissions:
   ```python
   policy = GitHubPolicy(
       allow_push=True,          # Enable push
       allow_create_pr=True,     # Enable PR creation
       allow_comment=True,       # Enable commenting
   )
   ```

2. Optionally disable Ask/Stop gates (not recommended for production):
   ```python
   policy = GitHubPolicy(
       allow_push=True,
       require_ask_stop_for_push=False,  # ⚠️ Dangerous!
   )
   ```

3. Add repos to allowlist:
   ```python
   policy = GitHubPolicy(
       allowed_owner_repos={
           "WoltLab51/Genus",
           "WoltLab51/OtherRepo",
       }
   )
   ```

## Memory Journal Integration

All GitHub operations are logged to the run journal:

```python
# Example journal events:
{
    "ts": "2026-04-06T16:00:00Z",
    "phase": "github",
    "event_type": "tool_used",
    "summary": "Used tool: github_push_branch",
    "data": {
        "tool_name": "github_push_branch",
        "remote": "origin",
        "branch": "feature/test"
    }
}

{
    "ts": "2026-04-06T16:00:10Z",
    "phase": "github",
    "event_type": "pr_created",
    "summary": "Created PR #123: feat: add new feature",
    "data": {
        "pr_url": "https://github.com/WoltLab51/Genus/pull/123",
        "pr_number": 123,
        "action": "created",
        "head": "feature/test",
        "base": "main"
    }
}
```

**Security**: Tokens and credentials are **never** logged.

## CI Checks Polling

Monitor GitHub Actions and CI checks:

```python
result = await github_wait_for_checks(
    client=client,
    config=config,
    ref="feature/test",
    timeout_s=600,        # Max 10 minutes
    poll_interval_s=30,   # Check every 30 seconds
    journal=journal,
)

# Result data:
{
    "conclusion": "success",  # "success", "failure", or "timeout"
    "total_checks": 5,
    "passed": 5,
    "failed": 0,
    "pending": 0,
    "failing_checks": []  # List of failed checks if any
}
```

## Error Handling

All tools return `ToolResult` with consistent error handling:

```python
result = await github_push_branch(...)

if result.success:
    # Operation succeeded
    data = result.data
else:
    # Operation failed
    error = result.error
    print(f"Error: {error}")
```

Common errors:

- `GitHubPolicyError`: Operation denied by policy
- `GitHubAPIError`: GitHub API request failed (rate limit, auth, etc.)
- `RuntimeError`: Missing `GITHUB_TOKEN` environment variable
- `SandboxPolicyError`: Git command not allowed by sandbox policy
- `KillSwitchError`: Kill-switch is disabled

## Testing

All components include comprehensive unit tests with mocked HTTP:

```bash
# Run GitHub tests
pytest tests/unit/test_github_auth.py
pytest tests/unit/test_github_policy.py
pytest tests/unit/test_github_client.py
pytest tests/unit/test_tools_github_pr.py

# Run all tests
pytest tests/unit/
```

Tests use mocked HTTP responses (no real GitHub API calls).

## Future Enhancements

Potential improvements for future versions:

1. **Smarter Ask/Stop gates**: Context-aware confirmation logic
2. **Batch operations**: Multiple PRs/comments in one call
3. **PR review automation**: Automated code review comments
4. **Label management**: Auto-label PRs based on content
5. **Merge queue integration**: Coordinate with GitHub merge queues
6. **GraphQL API**: More efficient queries for complex operations

## Security Checklist

Before enabling GitHub automation in production:

- [ ] `GITHUB_TOKEN` stored securely (not in code)
- [ ] Token has minimum required scopes
- [ ] `allowed_owner_repos` limited to necessary repos
- [ ] Ask/Stop gates enabled for sensitive operations
- [ ] Journal logging configured and monitored
- [ ] Kill-switch mechanism tested and working
- [ ] Error handling and logging reviewed

## Troubleshooting

### "GitHub token not found"

**Problem**: `GITHUB_TOKEN` environment variable not set.

**Solution**:
```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

### "Action 'push' is not allowed by policy"

**Problem**: GitHubPolicy has `allow_push=False` (default).

**Solution**:
```python
policy = GitHubPolicy(allow_push=True)
```

### "Repository 'owner/repo' is not in allowlist"

**Problem**: Repo not in `allowed_owner_repos`.

**Solution**:
```python
policy = GitHubPolicy(
    allowed_owner_repos={"owner/repo"}
)
```

### "API rate limit exceeded"

**Problem**: GitHub API rate limit reached (5000 requests/hour authenticated).

**Solution**: Wait for rate limit reset or optimize polling intervals.

### "Kill-switch is disabled"

**Problem**: Sandbox kill-switch is off (safety mechanism).

**Solution**: Re-enable kill-switch:
```python
from genus.security.kill_switch import DEFAULT_KILL_SWITCH
DEFAULT_KILL_SWITCH.enable()
```

## Support

For issues or questions:
- Check existing issues: https://github.com/WoltLab51/Genus/issues
- Create new issue: https://github.com/WoltLab51/Genus/issues/new
- Review PR #29 for implementation details
