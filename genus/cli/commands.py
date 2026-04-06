"""
CLI Commands Module

Implements the core CLI command functions: run, resume, report.
Each command is an async function that returns an exit code.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from genus.cli.config import CliConfig
from genus.cli.report import generate_report
from genus.communication.message_bus import MessageBus
from genus.core.run import new_run_id, attach_run_id
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.workspace.workspace import RunWorkspace


async def cmd_run(
    goal: str,
    config: CliConfig,
    requirements: Optional[list] = None,
    constraints: Optional[list] = None,
    workspace_root: Optional[Path] = None,
    branch: Optional[str] = None,
) -> int:
    """Execute a new GENUS run.

    Args:
        goal: High-level description of the run's objective.
        config: CLI configuration.
        requirements: Optional list of requirements.
        constraints: Optional list of constraints.
        workspace_root: Optional workspace root (overrides config).
        branch: Optional git branch name.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    try:
        # Generate run_id
        run_id = new_run_id(slug=goal[:32] if goal else "run")
        print(f"Starting new GENUS run: {run_id}")

        # Initialize workspace using RunWorkspace
        ws_root = workspace_root or config.workspace_root
        workspace = RunWorkspace.create(run_id, workspace_root=ws_root)
        workspace.ensure_dirs()
        print(f"Workspace: {workspace.root}")

        # Initialize run journal
        store = JsonlRunStore(base_dir=str(config.get_runs_store_dir()))
        journal = RunJournal(run_id, store)

        # Create run header
        repo_id = None
        if config.github_owner and config.github_repo:
            repo_id = f"{config.github_owner}/{config.github_repo}"

        header = journal.initialize(
            goal=goal,
            repo_id=repo_id,
            workspace_root=str(workspace.root),
            requirements=requirements or [],
            constraints=constraints or [],
            branch=branch,
        )
        print(f"Initialized run journal at: {store.base_dir / run_id}")

        # Create message bus
        bus = MessageBus()

        # Import and start agents
        from genus.dev.agents.planner_agent import PlannerAgent
        from genus.dev.agents.builder_agent import BuilderAgent
        from genus.dev.agents.tester_agent import TesterAgent
        from genus.dev.agents.reviewer_agent import ReviewerAgent
        from genus.meta.agents.evaluation_agent import EvaluationAgent

        # Start agents
        print("Starting agents...")
        planner = PlannerAgent(bus, "planner-1")
        builder = BuilderAgent(bus, "builder-1")
        tester = TesterAgent(bus, "tester-1")
        reviewer = ReviewerAgent(bus, "reviewer-1")
        evaluator = EvaluationAgent(bus, "evaluator-1", store=store)

        planner.start()
        builder.start()
        tester.start()
        reviewer.start()
        evaluator.start()

        # Run orchestrator
        from genus.dev.devloop_orchestrator import DevLoopOrchestrator

        print("Running orchestrator...")
        orchestrator = DevLoopOrchestrator(
            bus,
            sender_id="cli-orchestrator",
            timeout_s=300.0,  # 5 minute timeout
            max_iterations=3,
        )

        try:
            await orchestrator.run(
                run_id=run_id,
                goal=goal,
                requirements=requirements,
                constraints=constraints,
                context={
                    "workspace_root": str(workspace.root),
                    "branch": branch,
                    "repo_id": repo_id,
                },
            )
            print("Run completed successfully.")
            status = 0
        except Exception as exc:
            print(f"Run failed: {exc}", file=sys.stderr)
            journal.log_error("orchestrator", f"Run failed: {exc}")
            status = 1
        finally:
            # Stop agents
            planner.stop()
            builder.stop()
            tester.stop()
            reviewer.stop()
            evaluator.stop()

        # Generate and print report
        report_path = store.base_dir / run_id / "report.txt"
        report_text = generate_report(run_id, store, format="text")
        report_path.write_text(report_text, encoding="utf-8")
        print(f"\nReport saved to: {report_path}")
        print("\nRun Summary:")
        print(report_text[:500])  # Print first 500 chars

        return status

    except Exception as exc:
        print(f"Error running GENUS: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


async def cmd_resume(
    run_id: str,
    config: CliConfig,
    force: bool = False,
) -> int:
    """Resume an interrupted GENUS run.

    Args:
        run_id: The run identifier to resume.
        config: CLI configuration.
        force: Force resume even if the run completed or requires confirmation.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    try:
        # Load run journal
        store = JsonlRunStore(base_dir=str(config.get_runs_store_dir()))
        journal = RunJournal(run_id, store)

        if not journal.exists():
            print(f"Error: Run {run_id} not found.", file=sys.stderr)
            return 1

        header = journal.get_header()
        if not header:
            print(f"Error: Run {run_id} has no header.", file=sys.stderr)
            return 1

        print(f"Resuming run: {run_id}")
        print(f"Goal: {header.goal}")

        # Check run status
        events = journal.get_events()
        if not events:
            print("Warning: No events found. Run may not have started.")

        # Determine last state
        last_event = events[-1] if events else None
        if last_event:
            print(f"Last event: {last_event.phase} - {last_event.event_type}: {last_event.summary}")

            # Check if run is already completed
            if last_event.phase == "orchestrator" and last_event.event_type == "completed":
                print("Run already completed.")
                # Just print the report
                report = generate_report(run_id, store, format="text")
                print("\n" + report)
                return 0

            # Check if run failed with AskStop
            if last_event.event_type == "failed" and "operator" in last_event.summary.lower():
                if not force:
                    print("Run failed and is awaiting operator confirmation.")
                    print("Use --force to resume anyway.")
                    return 1

        # TODO: Implement actual resume logic
        # For now, just generate a report
        print("\nNote: Resume functionality is not yet fully implemented.")
        print("Generating report for current state...\n")

        report = generate_report(run_id, store, format="text")
        print(report)

        return 2  # Exit code 2 indicates TODO/not implemented

    except Exception as exc:
        print(f"Error resuming run: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_report(
    run_id: str,
    config: CliConfig,
    format: str = "text",
    output: Optional[Path] = None,
) -> int:
    """Generate and display a report for a run.

    Args:
        run_id: The run identifier.
        config: CLI configuration.
        format: Output format ("text" or "md").
        output: Optional output file path.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    try:
        # Load run journal
        store = JsonlRunStore(base_dir=str(config.get_runs_store_dir()))

        if not store.run_exists(run_id):
            print(f"Error: Run {run_id} not found.", file=sys.stderr)
            return 1

        # Generate report
        report = generate_report(run_id, store, format=format)

        # Output report
        if output:
            output.write_text(report, encoding="utf-8")
            print(f"Report saved to: {output}")
        else:
            print(report)

        return 0

    except Exception as exc:
        print(f"Error generating report: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
