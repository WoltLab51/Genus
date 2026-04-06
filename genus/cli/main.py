"""
GENUS CLI Main Entry Point

Command-line interface for GENUS autonomous development system.
Provides run, resume, and report commands.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from genus.cli.commands import cmd_run, cmd_resume, cmd_report
from genus.cli.config import CliConfig


def parse_args(argv=None):
    """Parse command line arguments.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="genus",
        description="GENUS - Autonomous Software Development System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Root directory for workspaces (default: ~/genus-workspaces)",
    )
    parser.add_argument(
        "--runs-store-dir",
        type=Path,
        help="Directory for run journals (default: workspace-root/var/runs)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Start a new GENUS run",
        description="Start a new GENUS autonomous development run.",
    )
    run_parser.add_argument(
        "--goal",
        required=True,
        help="High-level goal or objective for this run",
    )
    run_parser.add_argument(
        "--requirements",
        nargs="+",
        help="List of requirements or acceptance criteria",
    )
    run_parser.add_argument(
        "--constraints",
        nargs="+",
        help="List of constraints or limitations",
    )
    run_parser.add_argument(
        "--branch",
        help="Git branch name to work on",
    )
    run_parser.add_argument(
        "--push",
        action="store_true",
        help="Enable git push to remote (requires GITHUB_TOKEN)",
    )
    run_parser.add_argument(
        "--create-pr",
        action="store_true",
        help="Enable PR creation (requires GITHUB_TOKEN)",
    )
    run_parser.add_argument(
        "--github-owner",
        help="GitHub repository owner (e.g., WoltLab51)",
    )
    run_parser.add_argument(
        "--github-repo",
        help="GitHub repository name (e.g., Genus)",
    )
    run_parser.add_argument(
        "--github-base-branch",
        default="main",
        help="Base branch for PRs (default: main)",
    )

    # Resume command
    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume an interrupted run",
        description="Resume a GENUS run that was interrupted or stopped.",
    )
    resume_parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier to resume",
    )
    resume_parser.add_argument(
        "--force",
        action="store_true",
        help="Force resume even if confirmation is required",
    )

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        help="Generate a run report",
        description="Generate and display a dashboard/report for a completed run.",
    )
    report_parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier to report on",
    )
    report_parser.add_argument(
        "--format",
        choices=["text", "md"],
        default="text",
        help="Output format: text (console) or md (markdown)",
    )
    report_parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: print to stdout)",
    )

    return parser.parse_args(argv)


def main(argv=None):
    """Main entry point for the GENUS CLI.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    args = parse_args(argv)

    # Check if a command was provided
    if not args.command:
        print("Error: No command specified. Use --help for usage information.", file=sys.stderr)
        return 1

    # Build configuration
    config = CliConfig(
        workspace_root=args.workspace_root or Path.home() / "genus-workspaces",
        runs_store_dir=args.runs_store_dir,
    )

    # Add GitHub config if provided
    if hasattr(args, "github_owner") and args.github_owner:
        config.github_owner = args.github_owner
    if hasattr(args, "github_repo") and args.github_repo:
        config.github_repo = args.github_repo
    if hasattr(args, "github_base_branch") and args.github_base_branch:
        config.github_base_branch = args.github_base_branch

    # Enable push/PR if requested
    if hasattr(args, "push") and args.push:
        config.push_enabled = True
    if hasattr(args, "create_pr") and args.create_pr:
        config.pr_creation_enabled = True

    # Execute command
    try:
        if args.command == "run":
            exit_code = asyncio.run(
                cmd_run(
                    goal=args.goal,
                    config=config,
                    requirements=args.requirements,
                    constraints=args.constraints,
                    workspace_root=args.workspace_root,
                    branch=args.branch,
                    push=args.push,
                    create_pr=args.create_pr,
                )
            )
        elif args.command == "resume":
            exit_code = asyncio.run(
                cmd_resume(
                    run_id=args.run_id,
                    config=config,
                    force=args.force,
                )
            )
        elif args.command == "report":
            exit_code = cmd_report(
                run_id=args.run_id,
                config=config,
                format=args.format,
                output=args.output,
            )
        else:
            print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
            exit_code = 1

        return exit_code

    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
