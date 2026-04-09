"""
Evaluation Data Models

Defines JSON-serializable dataclasses for evaluation input and output.
These models are designed to be simple, stable, and decoupled from other
GENUS modules.

All timestamp fields use ISO-8601 UTC strings for maximum interoperability.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationInput:
    """Input data for run evaluation.

    Attributes:
        run_id: Unique run identifier.
        goal: High-level goal/objective for the run (optional).
        final_status: Final status of the run ("completed" or "failed").
        iterations_used: Number of iterations/fix-loops executed.
        test_reports: List of test report artifacts (as dicts).
        github: Optional GitHub context (pr_url, checks summary).
        events: Optional subset of journal events for additional context.
        tool_context: Optional tool usage context from ToolMemoryIndex.
                      Dict with keys:
                      - "top_tools_fix": list of {tool_name, total_calls, calls_in_phase}
                        for top tools used in fix phase across recent runs
                      - "indexed_run_count": int, how many runs were indexed
    """
    run_id: str
    final_status: str  # Literal["completed", "failed"]
    iterations_used: int
    test_reports: List[Dict[str, Any]] = field(default_factory=list)
    goal: Optional[str] = None
    github: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    tool_context: Optional[Dict[str, Any]] = None


@dataclass
class EvaluationArtifact:
    """Evaluation output artifact.

    This artifact captures the evaluation results and is stored in the
    RunJournal for future reference. It provides both human-readable
    insights and machine-readable recommendations.

    Attributes:
        run_id: The run that was evaluated.
        created_at: ISO-8601 UTC timestamp when evaluation was performed.
        score: Quality score (0-100, higher is better).
        final_status: Final status of the run ("completed" or "failed").
        failure_class: Classification of failure (if failed), or None.
        root_cause_hint: Specific root cause hint (if available), or None.
        highlights: List of things that went well.
        issues: List of things that went wrong.
        recommendations: Human-readable recommendations for improvement.
        strategy_recommendations: Machine-readable strategy recommendations.
        evidence: Links to specific artifacts, log lines, or checks.
    """
    run_id: str
    created_at: str
    score: int
    final_status: str
    failure_class: Optional[str] = None
    root_cause_hint: Optional[str] = None
    highlights: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    strategy_recommendations: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
