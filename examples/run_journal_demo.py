#!/usr/bin/env python
"""
Demonstration of the Run Journal Store v1

Shows how to use the Run Journal Store to track a complete GENUS run
with phases, decisions, tool usage, and artifacts.
"""

from datetime import datetime, timezone

from genus.core.run import new_run_id
from genus.memory import ArtifactRecord, JournalEvent, JsonlRunStore, RunJournal


def demonstrate_run_journal():
    """Demonstrate a complete run journal workflow."""
    print("=" * 70)
    print("GENUS Run Journal Store v1 Demo")
    print("=" * 70)
    print()

    # 1. Create a store and journal
    print("1. Creating store and journal...")
    store = JsonlRunStore(base_dir="var/demo_runs")
    run_id = new_run_id(slug="demo-task")
    journal = RunJournal(run_id, store)
    print(f"   Run ID: {run_id}")
    print()

    # 2. Initialize the run
    print("2. Initializing run...")
    header = journal.initialize(
        goal="Demonstrate run journal store usage",
        repo_id="WoltLab51/Genus",
        workspace_root="/tmp/demo",
        priority="high",
        task_type="demo",
    )
    print(f"   Goal: {header.goal}")
    print(f"   Created: {header.created_at}")
    print()

    # 3. Log phase start: PLAN
    print("3. Starting PLAN phase...")
    journal.log_phase_start("plan", phase_id="plan_001")

    # 4. Log some decisions
    print("4. Logging decisions...")
    journal.log_decision(
        phase="plan",
        decision="Use modular architecture with clear separation of concerns",
        phase_id="plan_001",
        evidence=[
            {"type": "code_review", "file": "docs/ARCHITECTURE.md", "line": 10},
        ],
        rationale="Maintainability and testability",
    )
    journal.log_decision(
        phase="plan",
        decision="Store data in JSONL format for simplicity and auditability",
        phase_id="plan_001",
        evidence=[
            {"type": "requirement", "source": "problem_statement.md"},
        ],
    )

    # 5. Save a plan artifact
    print("5. Saving plan artifact...")
    plan_id = journal.save_artifact(
        phase="plan",
        artifact_type="plan",
        payload={
            "title": "Run Journal Store Implementation Plan",
            "steps": [
                "Create data models",
                "Implement storage backend",
                "Add high-level API",
                "Write comprehensive tests",
            ],
            "estimated_files": 4,
        },
        phase_id="plan_001",
        evidence=[
            {"type": "requirement", "source": "problem_statement.md"},
        ],
    )
    print(f"   Plan artifact ID: {plan_id}")
    print()

    # 6. Log phase start: IMPLEMENT
    print("6. Starting IMPLEMENT phase...")
    journal.log_phase_start("implement", phase_id="impl_001")

    # 7. Log tool usage
    print("7. Logging tool usage...")
    journal.log_tool_use(
        phase="implement",
        tool_name="grep",
        phase_id="impl_001",
        pattern="EventStore",
        matches=15,
    )
    journal.log_tool_use(
        phase="implement",
        tool_name="edit",
        phase_id="impl_001",
        file="genus/memory/models.py",
        changes=3,
    )

    # 8. Log an error (recovered)
    print("8. Logging error (recovered)...")
    journal.log_error(
        phase="implement",
        error="Import cycle detected between models and run_journal",
        phase_id="impl_001",
        exception_type="ImportError",
        resolution="Decoupled by using primitive dicts in models",
    )

    # 9. Log phase start: TEST
    print("9. Starting TEST phase...")
    journal.log_phase_start("test", phase_id="test_001")

    # 10. Save test report artifact
    print("10. Saving test report artifact...")
    test_report_id = journal.save_artifact(
        phase="test",
        artifact_type="test_report",
        payload={
            "total_tests": 44,
            "passed": 44,
            "failed": 0,
            "coverage": 98.5,
            "duration_seconds": 0.14,
        },
        phase_id="test_001",
    )
    print(f"   Test report artifact ID: {test_report_id}")
    print()

    # 11. Query the journal
    print("11. Querying journal...")
    all_events = journal.get_events()
    print(f"   Total events: {len(all_events)}")

    decisions = journal.get_events(event_type="decision")
    print(f"   Decisions: {len(decisions)}")
    for decision in decisions:
        print(f"      - {decision.summary}")

    tool_uses = journal.get_events(event_type="tool_used")
    print(f"   Tool uses: {len(tool_uses)}")
    for tool_use in tool_uses:
        print(f"      - {tool_use.data.get('tool_name', 'unknown')}")

    print()

    # 12. Query artifacts
    print("12. Querying artifacts...")
    all_artifacts = journal.list_artifacts()
    print(f"   Total artifacts: {len(all_artifacts)}")

    plans = journal.list_artifacts(artifact_type="plan")
    print(f"   Plans: {len(plans)}")

    test_reports = journal.list_artifacts(artifact_type="test_report")
    print(f"   Test reports: {len(test_reports)}")
    print()

    # 13. Load and inspect an artifact
    print("13. Inspecting plan artifact...")
    plan = journal.load_artifact(plan_id)
    if plan:
        print(f"   Artifact type: {plan.artifact_type}")
        print(f"   Phase: {plan.phase}")
        print(f"   Saved at: {plan.saved_at}")
        print(f"   Steps in plan: {len(plan.payload.get('steps', []))}")
    print()

    # 14. Verify storage layout
    print("14. Verifying storage layout...")
    print(f"   Run exists: {journal.exists()}")
    header = journal.get_header()
    if header:
        print(f"   Header goal: {header.goal}")
        print(f"   Header meta keys: {list(header.meta.keys())}")
    print()

    # 15. List all runs in store
    print("15. Listing all runs in store...")
    all_runs = store.list_runs()
    print(f"   Total runs: {len(all_runs)}")
    for run in all_runs[-3:]:  # Show last 3
        print(f"      - {run}")
    print()

    print("=" * 70)
    print("Demo complete! Check var/demo_runs/ for the generated files.")
    print("=" * 70)


if __name__ == "__main__":
    demonstrate_run_journal()
