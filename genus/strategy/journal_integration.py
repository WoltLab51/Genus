"""
Strategy Journal Integration

Helper functions for integrating strategy decisions with RunJournal.
Provides convenient methods for logging strategy decisions and artifacts.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from genus.memory.run_journal import RunJournal

from genus.strategy.models import StrategyDecision


def log_strategy_decision(
    journal: "RunJournal",
    decision: StrategyDecision,
    phase_id: Optional[str] = None,
) -> None:
    """Log a strategy decision to the run journal.

    Records the strategy decision as both a decision event and an artifact
    for full traceability.

    Args:
        journal: The RunJournal instance.
        decision: The StrategyDecision to log.
        phase_id: Optional phase instance identifier.
    """
    # Log as decision event
    journal.log_decision(
        phase=decision.phase,
        decision=f"Selected strategy: {decision.selected_playbook}",
        phase_id=phase_id,
        reason=decision.reason,
        playbook_id=decision.selected_playbook,
        candidates=decision.candidates,
        iteration=decision.iteration,
    )

    # Save as artifact for future reference
    journal.save_artifact(
        phase=decision.phase,
        artifact_type="strategy_decision",
        payload=decision.to_dict(),
        phase_id=phase_id,
    )


def get_last_strategy_decision(
    journal: "RunJournal",
    phase: Optional[str] = None,
) -> Optional[StrategyDecision]:
    """Get the most recent strategy decision from the journal.

    Args:
        journal: The RunJournal instance.
        phase: Optional filter by phase.

    Returns:
        The most recent StrategyDecision if found, otherwise None.
    """
    artifacts = journal.get_artifacts(
        phase=phase,
        artifact_type="strategy_decision",
    )

    if not artifacts:
        return None

    # Return most recent (last in list)
    latest = artifacts[-1]
    return StrategyDecision.from_dict(latest.payload)


def get_all_strategy_decisions(
    journal: "RunJournal",
    phase: Optional[str] = None,
) -> list:
    """Get all strategy decisions from the journal.

    Args:
        journal: The RunJournal instance.
        phase: Optional filter by phase.

    Returns:
        List of StrategyDecision objects, ordered chronologically.
    """
    artifacts = journal.get_artifacts(
        phase=phase,
        artifact_type="strategy_decision",
    )

    return [StrategyDecision.from_dict(a.payload) for a in artifacts]
