"""
CLI Report Generator

Generates human-readable reports and dashboards from run journals.
Supports both text (console) and markdown (GitHub-friendly) formats.
"""

from typing import List, Optional
from genus.memory.store_jsonl import JsonlRunStore
from genus.memory.run_journal import RunJournal
from genus.memory.models import JournalEvent, ArtifactRecord


def generate_report(run_id: str, store: JsonlRunStore, *, format: str = "text") -> str:
    """Generate a comprehensive report from a run journal.

    Args:
        run_id: The run identifier.
        store: JsonlRunStore instance containing the run data.
        format: Output format - "text" for console, "md" for markdown.

    Returns:
        Formatted report string.
    """
    # Create journal reader
    journal = RunJournal(run_id, store)

    # Load run data
    header = journal.get_header()
    if not header:
        return f"Error: Run {run_id} not found."

    events = journal.get_events()

    # Build report sections
    if format == "md":
        return _generate_markdown_report(run_id, header, events, store)
    else:
        return _generate_text_report(run_id, header, events, store)


def _generate_text_report(run_id: str, header, events: List[JournalEvent], store: JsonlRunStore) -> str:
    """Generate a console-friendly text report."""
    lines = []

    # Header
    lines.append("=" * 80)
    lines.append(f"GENUS Run Report: {run_id}")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Created:  {header.created_at}")
    lines.append(f"Goal:     {header.goal}")
    if header.repo_id:
        lines.append(f"Repo:     {header.repo_id}")
    if header.workspace_root:
        lines.append(f"Workspace: {header.workspace_root}")

    # Determine final status
    status = _determine_status(events)
    lines.append(f"Status:   {status}")
    lines.append("")

    # Timeline summary
    lines.append("-" * 80)
    lines.append("Timeline")
    lines.append("-" * 80)
    phase_events = [e for e in events if e.event_type in ("started", "completed", "failed")]
    if phase_events:
        for event in phase_events[:10]:  # Show first 10 phase transitions
            lines.append(f"  {event.ts[:19]} | {event.phase:12} | {event.event_type:10} | {event.summary}")
    else:
        lines.append("  No phase events recorded.")
    lines.append("")

    # Iterations
    lines.append("-" * 80)
    lines.append("Iterations")
    lines.append("-" * 80)
    iterations = _extract_iterations(events, store)
    if iterations:
        for iteration in iterations:
            lines.append(f"  Iteration {iteration['number']}:")
            if iteration.get('commits'):
                for commit in iteration['commits']:
                    lines.append(f"    - Commit: {commit}")
    else:
        lines.append("  No iterations recorded.")
    lines.append("")

    # Tests
    lines.append("-" * 80)
    lines.append("Test Results")
    lines.append("-" * 80)
    test_reports = _get_test_reports(store, run_id)
    if test_reports:
        for i, report in enumerate(test_reports[-3:], 1):  # Show last 3 test reports
            payload = report.payload
            lines.append(f"  Test Report {i}:")
            lines.append(f"    Exit Code: {payload.get('exit_code', 'N/A')}")
            lines.append(f"    Duration:  {payload.get('duration', 'N/A')}s")
            lines.append(f"    Timed Out: {payload.get('timed_out', False)}")
            if payload.get('stderr'):
                stderr_tail = payload['stderr'][-200:] if len(payload['stderr']) > 200 else payload['stderr']
                lines.append(f"    Stderr:    {stderr_tail}")
    else:
        lines.append("  No test reports found.")
    lines.append("")

    # GitHub
    lines.append("-" * 80)
    lines.append("GitHub")
    lines.append("-" * 80)
    pr_info = _get_pr_info(store, run_id)
    if pr_info:
        lines.append(f"  PR URL:    {pr_info.get('pr_url', 'N/A')}")
        lines.append(f"  PR Number: {pr_info.get('pr_number', 'N/A')}")
        if pr_info.get('checks'):
            lines.append(f"  Checks:    {pr_info['checks']}")
    else:
        lines.append("  No PR information found.")
    lines.append("")

    # Evaluation
    lines.append("-" * 80)
    lines.append("Evaluation")
    lines.append("-" * 80)
    evaluation = _get_evaluation(store, run_id)
    if evaluation:
        lines.append(f"  Score:         {evaluation.get('score', 'N/A')}")
        lines.append(f"  Failure Class: {evaluation.get('failure_class', 'N/A')}")
        if evaluation.get('root_cause_hint'):
            lines.append(f"  Root Cause:    {evaluation['root_cause_hint']}")
        if evaluation.get('recommendations'):
            lines.append("  Recommendations:")
            for rec in evaluation['recommendations']:
                lines.append(f"    - {rec}")
    else:
        lines.append("  No evaluation found.")
    lines.append("")

    # Strategy
    lines.append("-" * 80)
    lines.append("Strategy Decisions")
    lines.append("-" * 80)
    strategies = _get_strategy_decisions(store, run_id)
    if strategies:
        for i, strategy in enumerate(strategies, 1):
            lines.append(f"  Decision {i}:")
            lines.append(f"    Playbook: {strategy.get('selected_playbook', 'N/A')}")
            lines.append(f"    Reason:   {strategy.get('reason', 'N/A')}")
            if strategy.get('candidates'):
                lines.append(f"    Candidates: {', '.join(strategy['candidates'])}")
    else:
        lines.append("  No strategy decisions found.")
    lines.append("")

    lines.append("=" * 80)

    return "\n".join(lines)


def _generate_markdown_report(run_id: str, header, events: List[JournalEvent], store: JsonlRunStore) -> str:
    """Generate a GitHub-friendly markdown report."""
    lines = []

    # Header
    lines.append(f"# GENUS Run Report: {run_id}")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Created:** {header.created_at}")
    lines.append(f"- **Goal:** {header.goal}")
    if header.repo_id:
        lines.append(f"- **Repository:** {header.repo_id}")
    if header.workspace_root:
        lines.append(f"- **Workspace:** {header.workspace_root}")

    status = _determine_status(events)
    lines.append(f"- **Status:** {status}")
    lines.append("")

    # Timeline
    lines.append("## Timeline")
    lines.append("")
    phase_events = [e for e in events if e.event_type in ("started", "completed", "failed")]
    if phase_events:
        for event in phase_events[:10]:
            lines.append(f"- `{event.ts[:19]}` **{event.phase}** - {event.event_type}: {event.summary}")
    else:
        lines.append("No phase events recorded.")
    lines.append("")

    # Iterations
    lines.append("## Iterations")
    lines.append("")
    iterations = _extract_iterations(events, store)
    if iterations:
        for iteration in iterations:
            lines.append(f"### Iteration {iteration['number']}")
            if iteration.get('commits'):
                for commit in iteration['commits']:
                    lines.append(f"- Commit: `{commit}`")
    else:
        lines.append("No iterations recorded.")
    lines.append("")

    # Tests
    lines.append("## Test Results")
    lines.append("")
    test_reports = _get_test_reports(store, run_id)
    if test_reports:
        for i, report in enumerate(test_reports[-3:], 1):
            payload = report.payload
            lines.append(f"### Test Report {i}")
            lines.append("")
            lines.append(f"- **Exit Code:** {payload.get('exit_code', 'N/A')}")
            lines.append(f"- **Duration:** {payload.get('duration', 'N/A')}s")
            lines.append(f"- **Timed Out:** {payload.get('timed_out', False)}")
            if payload.get('stderr'):
                stderr_tail = payload['stderr'][-500:] if len(payload['stderr']) > 500 else payload['stderr']
                lines.append("")
                lines.append("**Error Output:**")
                lines.append("```")
                lines.append(stderr_tail)
                lines.append("```")
            lines.append("")
    else:
        lines.append("No test reports found.")
    lines.append("")

    # GitHub
    lines.append("## GitHub")
    lines.append("")
    pr_info = _get_pr_info(store, run_id)
    if pr_info:
        pr_url = pr_info.get('pr_url', 'N/A')
        lines.append(f"- **PR URL:** {pr_url}")
        lines.append(f"- **PR Number:** {pr_info.get('pr_number', 'N/A')}")
        if pr_info.get('checks'):
            lines.append(f"- **Checks:** {pr_info['checks']}")
    else:
        lines.append("No PR information found.")
    lines.append("")

    # Evaluation
    lines.append("## Evaluation")
    lines.append("")
    evaluation = _get_evaluation(store, run_id)
    if evaluation:
        lines.append(f"- **Score:** {evaluation.get('score', 'N/A')}")
        lines.append(f"- **Failure Class:** {evaluation.get('failure_class', 'N/A')}")
        if evaluation.get('root_cause_hint'):
            lines.append(f"- **Root Cause:** {evaluation['root_cause_hint']}")
        if evaluation.get('recommendations'):
            lines.append("")
            lines.append("**Recommendations:**")
            for rec in evaluation['recommendations']:
                lines.append(f"- {rec}")
    else:
        lines.append("No evaluation found.")
    lines.append("")

    # Strategy
    lines.append("## Strategy Decisions")
    lines.append("")
    strategies = _get_strategy_decisions(store, run_id)
    if strategies:
        for i, strategy in enumerate(strategies, 1):
            lines.append(f"### Decision {i}")
            lines.append("")
            lines.append(f"- **Playbook:** {strategy.get('selected_playbook', 'N/A')}")
            lines.append(f"- **Reason:** {strategy.get('reason', 'N/A')}")
            if strategy.get('candidates'):
                lines.append(f"- **Candidates:** {', '.join(strategy['candidates'])}")
            lines.append("")
    else:
        lines.append("No strategy decisions found.")
    lines.append("")

    return "\n".join(lines)


# Helper functions

def _determine_status(events: List[JournalEvent]) -> str:
    """Determine the final status from journal events."""
    if not events:
        return "unknown"

    # Check for loop completion/failure events
    for event in reversed(events):
        if event.phase == "orchestrator" or "loop" in event.phase:
            if event.event_type == "completed":
                return "completed"
            elif event.event_type == "failed":
                return "failed"

    # Check last event
    last = events[-1]
    if last.event_type == "error":
        return "failed"
    elif last.event_type == "completed":
        return "completed"

    return "in_progress"


def _extract_iterations(events: List[JournalEvent], store: JsonlRunStore) -> List[dict]:
    """Extract iteration information from events."""
    iterations = {}

    for event in events:
        iteration = event.data.get('iteration')
        if iteration is not None:
            if iteration not in iterations:
                iterations[iteration] = {'number': iteration, 'commits': []}

            # Look for commit information
            if 'commit_sha' in event.data:
                iterations[iteration]['commits'].append(event.data['commit_sha'])

    return sorted(iterations.values(), key=lambda x: x['number'])


def _get_test_reports(store: JsonlRunStore, run_id: str) -> List[ArtifactRecord]:
    """Get test report artifacts."""
    journal = RunJournal(run_id, store)
    artifact_ids = journal.list_artifacts(artifact_type="test_report")
    reports = []
    for artifact_id in artifact_ids:
        artifact = journal.load_artifact(artifact_id)
        if artifact:
            reports.append(artifact)
    return reports


def _get_pr_info(store: JsonlRunStore, run_id: str) -> Optional[dict]:
    """Get PR information from artifacts."""
    journal = RunJournal(run_id, store)
    artifact_ids = journal.list_artifacts(artifact_type="pr_info")
    if not artifact_ids:
        return None

    # Get the most recent PR info
    artifact = journal.load_artifact(artifact_ids[-1])
    return artifact.payload if artifact else None


def _get_evaluation(store: JsonlRunStore, run_id: str) -> Optional[dict]:
    """Get evaluation artifact."""
    journal = RunJournal(run_id, store)
    artifact_ids = journal.list_artifacts(artifact_type="evaluation")
    if not artifact_ids:
        return None

    # Get the most recent evaluation
    artifact = journal.load_artifact(artifact_ids[-1])
    return artifact.payload if artifact else None


def _get_strategy_decisions(store: JsonlRunStore, run_id: str) -> List[dict]:
    """Get all strategy decision artifacts."""
    journal = RunJournal(run_id, store)
    artifact_ids = journal.list_artifacts(artifact_type="strategy_decision")
    decisions = []
    for artifact_id in artifact_ids:
        artifact = journal.load_artifact(artifact_id)
        if artifact:
            decisions.append(artifact.payload)
    return decisions
