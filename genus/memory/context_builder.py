"""
Episodic Context Builder

Builds LLM-readable context summaries from historical run journals.
Used by agents that need to inject past-run knowledge into prompts.

Design:
- Read-only access to RunJournal
- Returns structured dicts (JSON-serializable) and plain text summaries
- Never loads full journal — only targeted artifact types
- Gracefully handles missing artifacts

Note: For token-budget-aware planner formatting, see
genus/dev/context_formatter.format_episodic_for_planner()
"""

from typing import Any, Dict, List, Optional

from genus.memory.models import RunHeader
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore


def build_run_summary(
    run_id: str,
    store: JsonlRunStore,
) -> Optional[Dict[str, Any]]:
    """Build a structured summary dict for a single run.

    Loads only the artifacts relevant for LLM context:
    - RunHeader (goal, repo_id, created_at)
    - Latest evaluation artifact (score, failure_class, strategy_recommendations)
    - Latest feedback_record artifact (outcome, score_delta)
    - Latest strategy_decision artifact (selected_playbook)

    Args:
        run_id: The run identifier.
        store: The JsonlRunStore backend.

    Returns:
        A JSON-serializable dict with run summary, or None if the run
        has no header (e.g. orphaned directory).

    Example return value::

        {
            "run_id": "run-2024-01-15-001",
            "goal": "Fix failing test in genus/sandbox/runner.py",
            "repo_id": "WoltLab51/Genus",
            "created_at": "2024-01-15T10:00:00+00:00",
            "evaluation": {
                "score": 85,
                "failure_class": None,
                "strategy_recommendations": ["minimize_changeset"],
            },
            "feedback": {
                "outcome": "good",
                "score_delta": 3.0,
            },
            "strategy": {
                "selected_playbook": "fix_tests",
            },
        }
    """
    journal = RunJournal(run_id, store)
    header = journal.get_header()
    if header is None:
        return None

    summary: Dict[str, Any] = {
        "run_id": header.run_id,
        "goal": header.goal,
        "repo_id": header.repo_id,
        "created_at": header.created_at,
        "evaluation": None,
        "feedback": None,
        "strategy": None,
    }

    # Load latest evaluation artifact
    eval_artifacts = journal.get_artifacts(artifact_type="evaluation", phase="meta")
    if eval_artifacts:
        latest_eval = eval_artifacts[-1].payload
        summary["evaluation"] = {
            "score": latest_eval.get("score"),
            "failure_class": latest_eval.get("failure_class"),
            "strategy_recommendations": latest_eval.get("strategy_recommendations", []),
        }

    # Load latest feedback_record artifact
    feedback_artifacts = journal.get_artifacts(
        artifact_type="feedback_record", phase="feedback"
    )
    if feedback_artifacts:
        latest_feedback = feedback_artifacts[-1].payload
        summary["feedback"] = {
            "outcome": latest_feedback.get("outcome"),
            "score_delta": latest_feedback.get("score_delta"),
        }

    # Load latest strategy_decision artifact
    strategy_artifacts = journal.get_artifacts(
        artifact_type="strategy_decision", phase="strategy"
    )
    if strategy_artifacts:
        latest_strategy = strategy_artifacts[-1].payload
        summary["strategy"] = {
            "selected_playbook": latest_strategy.get("selected_playbook"),
        }

    return summary


def build_episodic_context(
    store: JsonlRunStore,
    *,
    run_ids: List[str],
    max_runs: int = 5,
) -> List[Dict[str, Any]]:
    """Build episodic context from multiple historical runs.

    Args:
        store: The JsonlRunStore backend.
        run_ids: List of run IDs to include (e.g. from query_runs()).
                 Processed in order; stops after max_runs valid summaries.
        max_runs: Maximum number of run summaries to return.

    Returns:
        List of run summary dicts (from build_run_summary()), ordered as
        provided in run_ids. Runs without a header are skipped.

    Example::

        from genus.memory.store_jsonl import JsonlRunStore
        from genus.memory.query import query_runs
        from genus.memory.context_builder import build_episodic_context

        store = JsonlRunStore()
        headers = query_runs(store, repo_id="WoltLab51/Genus", limit=10)
        context = build_episodic_context(
            store,
            run_ids=[h.run_id for h in headers],
            max_runs=5,
        )
        # context is a list of dicts ready for JSON serialization or prompt injection
    """
    summaries: List[Dict[str, Any]] = []

    for run_id in run_ids:
        if len(summaries) >= max_runs:
            break
        summary = build_run_summary(run_id, store)
        if summary is not None:
            summaries.append(summary)

    return summaries


def format_context_as_text(
    context: List[Dict[str, Any]],
) -> str:
    """Format episodic context as a human/LLM-readable text block.

    Args:
        context: List of run summary dicts from build_episodic_context().

    Returns:
        Formatted multi-line string suitable for injection into an LLM prompt.

    Example output::

        === Past Run Context (3 runs) ===

        [Run 1] run-2024-01-15-001
          Goal: Fix failing test in genus/sandbox/runner.py
          Repo: WoltLab51/Genus
          Date: 2024-01-15T10:00:00+00:00
          Evaluation: score=85, failure_class=None
          Strategy recommendations: minimize_changeset
          Feedback: outcome=good, score_delta=+3.0
          Selected playbook: fix_tests

        [Run 2] ...
    """
    if not context:
        return "=== Past Run Context (0 runs) ===\n(No historical runs available.)\n"

    lines = [f"=== Past Run Context ({len(context)} runs) ===\n"]

    for i, run in enumerate(context, start=1):
        lines.append(f"[Run {i}] {run['run_id']}")
        lines.append(f"  Goal: {run.get('goal', '(unknown)')}")
        if run.get("repo_id"):
            lines.append(f"  Repo: {run['repo_id']}")
        if run.get("created_at"):
            lines.append(f"  Date: {run['created_at']}")

        if run.get("evaluation"):
            ev = run["evaluation"]
            lines.append(
                f"  Evaluation: score={ev.get('score')}, "
                f"failure_class={ev.get('failure_class')}"
            )
            recs = ev.get("strategy_recommendations", [])
            if recs:
                lines.append(f"  Strategy recommendations: {', '.join(recs)}")

        if run.get("feedback"):
            fb = run["feedback"]
            delta = fb.get("score_delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"  Feedback: outcome={fb.get('outcome')}, "
                f"score_delta={sign}{delta}"
            )

        if run.get("strategy"):
            st = run["strategy"]
            if st.get("selected_playbook"):
                lines.append(f"  Selected playbook: {st['selected_playbook']}")

        lines.append("")  # blank line between runs

    return "\n".join(lines)
