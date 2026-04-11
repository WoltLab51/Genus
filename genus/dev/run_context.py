"""
RunContext — shared state for a single dev-loop run.

Passed to every PhaseRunner so they have access to all
shared resources without being tightly coupled to the orchestrator.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from genus.communication.message_bus import MessageBus
from genus.memory.run_journal import RunJournal

if TYPE_CHECKING:
    from genus.strategy.selector import StrategySelector


@dataclass
class PhaseTimeouts:
    """Per-phase timeout configuration in seconds.

    Attributes:
        plan:      Timeout for the plan phase.
        implement: Timeout for the implement phase.
        test:      Timeout for the test phase.
        fix:       Timeout for the fix phase.
        review:    Timeout for the review phase.
    """
    plan: float = 30.0
    implement: float = 30.0
    test: float = 30.0
    fix: float = 30.0
    review: float = 30.0


@dataclass
class RunContext:
    """Shared context for a single dev-loop run.

    Passed to every PhaseRunner. Holds all shared resources
    so runners do not need to be coupled to the orchestrator.

    Attributes:
        run_id:            Unique identifier for this run.
        goal:              Human-readable objective.
        bus:               The shared MessageBus instance.
        journal:           The RunJournal for this run.
        sender_id:         Identifier of the orchestrator component.
        timeouts:          Per-phase timeout configuration.
        strategy_selector: Optional strategy selector for fix phase.
        episodic_context:  Optional historical run context for the planner.
        context:           Optional extra context dict (e.g. agent_spec_template, domain).
    """
    run_id: str
    goal: str
    bus: MessageBus
    journal: RunJournal
    sender_id: str
    timeouts: PhaseTimeouts = field(default_factory=PhaseTimeouts)
    strategy_selector: "Optional[StrategySelector]" = None
    episodic_context: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None
