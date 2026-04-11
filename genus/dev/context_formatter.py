"""
EpisodicContext formatter for PlannerAgent — Phase 13c

Converts a list of episodic run-summary dicts into a token-budget-aware
plain-text block that can be prepended to the planner's system prompt.

Purely functional — no IO, no side effects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def format_episodic_for_planner(
    episodic_context: List[Dict[str, Any]],
    max_tokens_budget: int = 500,
) -> Optional[str]:
    """Format *episodic_context* into a compact text block for the PlannerAgent.

    Iterates over runs (oldest first), building one line per run.  Stops
    when the rough token estimate would exceed *max_tokens_budget*.
    Returns ``None`` when *episodic_context* is empty or no line fits.

    Token estimation uses a simple word-count × 1.3 heuristic — accurate
    enough for Raspberry-Pi token-budget awareness without importing a
    full tokeniser.

    Args:
        episodic_context:  List of run-summary dicts as produced by
                           ``genus.memory.context_builder.build_episodic_context``.
        max_tokens_budget: Upper bound for the total formatted output.
                           Default is Pi-safe (500 tokens).

    Returns:
        A formatted string starting with "Vorherige Runs:\\n…", or None.
    """
    if not episodic_context:
        return None

    lines: List[str] = []
    token_estimate: float = 0.0

    for run in episodic_context:
        goal = run.get("goal", "")
        summary = f"Früherer Run: {goal}"

        feedback = run.get("feedback") or {}
        outcome = feedback.get("outcome") if isinstance(feedback, dict) else None
        if outcome:
            summary += f" → {outcome}"

        evaluation = run.get("evaluation") or {}
        failure_class = (
            evaluation.get("failure_class")
            if isinstance(evaluation, dict)
            else None
        )
        if failure_class:
            summary += f" (Problem: {failure_class})"

        # Rough token estimate: words × 1.3
        token_estimate += len(summary.split()) * 1.3
        if token_estimate > max_tokens_budget:
            break

        lines.append(summary)

    if not lines:
        return None

    return "Vorherige Runs:\n" + "\n".join(f"- {line}" for line in lines)
