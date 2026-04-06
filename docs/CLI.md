# GENUS CLI Documentation

GENUS provides a command-line interface for managing autonomous software development runs. This document describes how to use the CLI on Windows, Linux, and macOS.

**Note**: GitHub push and PR creation features are planned for a future release. Currently, the CLI focuses on local run management and reporting.

## Installation

First, install GENUS with the CLI entry point:

```bash
pip install -e .
```

After installation, the `genus` command will be available in your terminal.

## Commands

### `genus run` - Start a New Run

Start a new autonomous development run.

**Basic Usage:**

```bash
genus run --goal "Your development goal here"
```

**Windows PowerShell Examples:**

```powershell
# Simple run
genus run --goal "Add user authentication"

# Run with requirements
genus run --goal "Implement search feature" --requirements "Must be fast" "Support fuzzy matching"

# Run with constraints
genus run --goal "Refactor database layer" --constraints "No breaking changes" "Maintain backwards compatibility"

# Specify custom workspace
genus run --goal "Build API endpoint" --workspace-root ~/genus-workspaces
```

**Linux/macOS Examples:**

```bash
# Simple run
genus run --goal "Add user authentication"

# Run with requirements
genus run --goal "Implement search feature" --requirements "Must be fast" "Support fuzzy matching"

# Run with constraints
genus run --goal "Refactor database layer" --constraints "No breaking changes" "Maintain backwards compatibility"

# Specify custom workspace
genus run --goal "Build API endpoint" --workspace-root ~/genus-workspaces
```

**Note**: The examples previously showing `--push` and `--create-pr` flags have been removed. GitHub publishing functionality will be added in a future release.

**Options:**

- `--goal` (required): High-level description of what to accomplish
- `--requirements`: List of requirements or acceptance criteria
- `--constraints`: List of constraints or limitations
- `--workspace-root`: Custom workspace directory (default: `~/genus-workspaces`)
- `--runs-store-dir`: Custom directory for run journals
- `--branch`: Git branch name to work on
- `--github-owner`: GitHub repository owner
- `--github-repo`: GitHub repository name
- `--github-base-branch`: Base branch for PRs (default: `main`)

**Note**: GitHub push and PR creation flags (`--push` and `--create-pr`) have been removed in favor of a more robust implementation coming in a future PR.

### `genus resume` - Resume an Interrupted Run

Resume a run that was interrupted, stopped, or failed.

**Basic Usage:**

```bash
genus resume --run-id <run_id>
```

**Windows PowerShell Examples:**

```powershell
# Resume a run
genus resume --run-id "2026-04-06T12-00-00Z__feature-auth__abc123"

# Force resume (bypass confirmation for stopped runs)
genus resume --run-id "2026-04-06T12-00-00Z__fix-bug__xyz789" --force
```

**Linux/macOS Examples:**

```bash
# Resume a run
genus resume --run-id "2026-04-06T12-00-00Z__feature-auth__abc123"

# Force resume (bypass confirmation for stopped runs)
genus resume --run-id "2026-04-06T12-00-00Z__fix-bug__xyz789" --force
```

**Options:**

- `--run-id` (required): The run identifier to resume
- `--force`: Force resume even if confirmation is required

**Note:** Resume functionality is currently limited. If a run is already completed, it will just display the report.

### `genus report` - Generate a Run Report

Generate and display a comprehensive dashboard/report for a run.

**Basic Usage:**

```bash
genus report --run-id <run_id>
```

**Windows PowerShell Examples:**

```powershell
# Display report in console
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123"

# Generate markdown report
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --format md

# Save report to file
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --output C:\reports\run-report.txt

# Generate markdown report and save to file
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --format md --output C:\reports\run-report.md
```

**Linux/macOS Examples:**

```bash
# Display report in console
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123"

# Generate markdown report
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --format md

# Save report to file
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --output ~/reports/run-report.txt

# Generate markdown report and save to file
genus report --run-id "2026-04-06T12-00-00Z__feature-auth__abc123" --format md --output ~/reports/run-report.md
```

**Options:**

- `--run-id` (required): The run identifier to report on
- `--format`: Output format - `text` (console-friendly) or `md` (markdown)
- `--output`: Output file path (default: print to stdout)

## Environment Variables

### `GENUS_RUNSTORE_DIR`

Override the default runs store directory. This is where run journals and artifacts are saved.

```bash
export GENUS_RUNSTORE_DIR="/custom/path/to/runs"
```

## Safety and Defaults

GENUS CLI is designed with **safety-first defaults**:

### Local Operation

By default, GENUS operates locally:
- All runs execute in isolated workspaces
- Run journals and artifacts are stored locally
- No automatic push or PR creation

### GitHub Integration (Future)

GitHub push and PR creation features are planned for a future release. When implemented, they will:
- Be disabled by default
- Require explicit user confirmation
- Validate required credentials before execution

### No Secrets in Output

The CLI will never print secrets or tokens in logs or reports.

## Report Contents

A GENUS report includes:

1. **Header**: Run ID, creation time, goal, repository, workspace path, final status
2. **Timeline**: Key phase transitions (plan, implement, test, review, fix)
3. **Iterations**: Implementation and fix iterations with commit information
4. **Test Results**: Exit codes, duration, error output from test runs
5. **GitHub**: PR URL, PR number, CI checks summary (if available)
6. **Evaluation**: Score, failure classification, root cause hints, recommendations
7. **Strategy Decisions**: Selected playbooks, reasoning, alternative candidates

## Finding Your Run ID

When you start a run, the CLI prints the run ID:

```
Starting new GENUS run: 2026-04-06T12-00-00Z__feature-auth__abc123
```

You can also find run IDs by looking in the runs store directory:

```bash
# Linux/macOS
ls ~/genus-workspaces/var/runs/

# Windows PowerShell
dir $HOME\genus-workspaces\var\runs\
```

## Troubleshooting

### "Command not found: genus"

Make sure you've installed GENUS:

```bash
pip install -e .
```

And that your Python scripts directory is in your PATH.

### "Error: Run <run_id> not found"

Check that:
1. The run ID is correct
2. You're using the correct `--runs-store-dir` if you customized it
3. The run directory exists in `~/genus-workspaces/var/runs/`

### "Error: GITHUB_TOKEN environment variable is required"

You need to set the `GITHUB_TOKEN` environment variable before using `--push` or `--create-pr`.

### Tests or builds fail during run

Check the report for detailed error messages:

```bash
genus report --run-id <your_run_id>
```

Look in the "Test Results" section for error output.

## Examples

### Complete Workflow

```bash
# 1. Start a new run
genus run --goal "Add password reset feature" \
  --requirements "Email-based reset" "15-minute token expiry" \
  --constraints "Use existing auth framework"

# Output shows run ID:
# Starting new GENUS run: 2026-04-06T14-30-00Z__add-password-reset-featur__k9x2q1

# 2. If interrupted, resume
genus resume --run-id "2026-04-06T14-30-00Z__add-password-reset-featur__k9x2q1"

# 3. Generate report
genus report --run-id "2026-04-06T14-30-00Z__add-password-reset-featur__k9x2q1"

# 4. Generate markdown report for documentation
genus report --run-id "2026-04-06T14-30-00Z__add-password-reset-featur__k9x2q1" \
  --format md --output password-reset-implementation.md
```

## Advanced Usage

### Custom Workspace Layout

```bash
# Use a project-specific workspace
genus run --goal "Implement feature X" \
  --workspace-root /projects/myapp/genus-workspace \
  --runs-store-dir /projects/myapp/genus-runs
```

### CI/CD Integration

```bash
#!/bin/bash
# run-genus-ci.sh

export GITHUB_TOKEN="${GITHUB_TOKEN}"

genus run --goal "${CI_GOAL}" \
  --requirements "${CI_REQUIREMENTS}" \
  --workspace-root /tmp/genus-ci \
  --push \
  --create-pr \
  --github-owner "${GITHUB_OWNER}" \
  --github-repo "${GITHUB_REPO}"

# Capture exit code
EXIT_CODE=$?

# Generate report regardless of success/failure
genus report --run-id "$(ls -t /tmp/genus-ci/var/runs/ | head -1)" \
  --format md --output run-report.md

exit $EXIT_CODE
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/WoltLab51/Genus/issues
- Documentation: https://github.com/WoltLab51/Genus/tree/main/docs
