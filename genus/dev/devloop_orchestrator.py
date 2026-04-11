"""
DevLoop Orchestrator

Coordinates autonomous dev-loop execution by sequencing PhaseRunners
and applying loop-level policies (Ask/Stop, max iterations).

Each phase is handled by a dedicated PhaseRunner in genus.dev.phase_runners.
Shared state is passed via RunContext from genus.dev.run_context.

Usage::

    orchestrator = DevLoopOrchestrator(bus, run_journal=journal, timeout_s=30.0)
    await orchestrator.run(run_id, goal="implement feature X")

Typical flow::

    dev.loop.started
      └─► PlanPhaseRunner   → dev.plan.requested / completed
            └─► ImplPhaseRunner  → dev.implement.requested / completed
                  └─► [TestPhaseRunner → FixPhaseRunner]* (max_iterations)
                        └─► ReviewPhaseRunner → dev.review.requested / completed
                              └─► Ask/Stop policy
                                    └─► dev.loop.completed / dev.loop.failed

If any phase fails or times out, the orchestrator publishes ``dev.loop.failed``
and terminates.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from genus.communication.message_bus import MessageBus
from genus.dev import events
from genus.dev.phase_runners import (
    FixPhaseRunner,
    ImplPhaseRunner,
    PlanPhaseRunner,
    ReviewPhaseRunner,
    TestPhaseRunner,
    _derive_recommendations,  # re-exported for backwards compatibility
)
from genus.dev.policy import should_ask_user
from genus.dev.run_context import PhaseTimeouts, RunContext
from genus.dev.runtime import DevResponseFailedError, DevResponseTimeoutError
from genus.memory.run_journal import RunJournal

if TYPE_CHECKING:
    from genus.strategy.selector import StrategySelector

logger = logging.getLogger(__name__)


class DevLoopOrchestrator:
    """Orchestrator that sequences dev-loop phases via PhaseRunners.

    Each phase is handled by a dedicated PhaseRunner. The orchestrator is
    responsible only for sequencing, loop control, and error routing.

    Args:
        bus:                   Shared :class:`~genus.communication.message_bus.MessageBus` instance.
        sender_id:             Identifier of this orchestrator (included in every message).
        timeout_s:             Default fallback timeout in seconds for all phases.
                               Acts as fallback for any per-phase timeout not set explicitly.
        max_iterations:        Maximum number of fix iterations if tests fail (default: 3).
        commit_each_iteration: Whether to commit after each fix iteration (default: True).
        run_journal:           Required :class:`~genus.memory.run_journal.RunJournal` instance.
                               All phase events and artifacts are written here.
        strategy_selector:     Optional :class:`~genus.strategy.selector.StrategySelector`
                               instance for fix-phase strategy selection.
        plan_timeout_s:        Override timeout for the plan phase.
        implement_timeout_s:   Override timeout for the implement phase.
        test_timeout_s:        Override timeout for the test phase.
        fix_timeout_s:         Override timeout for the fix phase.
        review_timeout_s:      Override timeout for the review phase.
    """

    def __init__(
        self,
        bus: MessageBus,
        sender_id: str = "DevLoopOrchestrator",
        timeout_s: float = 30.0,
        max_iterations: int = 3,
        commit_each_iteration: bool = True,
        *,
        run_journal: RunJournal,
        strategy_selector: "Optional[StrategySelector]" = None,
        plan_timeout_s: Optional[float] = None,
        implement_timeout_s: Optional[float] = None,
        test_timeout_s: Optional[float] = None,
        fix_timeout_s: Optional[float] = None,
        review_timeout_s: Optional[float] = None,
    ) -> None:
        self._bus = bus
        self._sender_id = sender_id
        self._timeout_s = timeout_s
        self._max_iterations = max_iterations
        self._commit_each_iteration = commit_each_iteration
        self._strategy_selector = strategy_selector
        self._run_journal = run_journal
        self._plan_timeout_s = plan_timeout_s if plan_timeout_s is not None else timeout_s
        self._implement_timeout_s = implement_timeout_s if implement_timeout_s is not None else timeout_s
        self._test_timeout_s = test_timeout_s if test_timeout_s is not None else timeout_s
        self._fix_timeout_s = fix_timeout_s if fix_timeout_s is not None else timeout_s
        self._review_timeout_s = review_timeout_s if review_timeout_s is not None else timeout_s

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, run_id: str, goal: str, context: Optional[Dict[str, Any]] = None) -> RunContext:
        """Build the RunContext for this run, including episodic context.

        Args:
            run_id:  Unique run identifier.
            goal:    Human-readable objective.
            context: Optional extra context dict (e.g. agent_spec_template, domain).

        Returns:
            A fully populated :class:`~genus.dev.run_context.RunContext`.
        """
        timeouts = PhaseTimeouts(
            plan=self._plan_timeout_s,
            implement=self._implement_timeout_s,
            test=self._test_timeout_s,
            fix=self._fix_timeout_s,
            review=self._review_timeout_s,
        )

        episodic_context = None
        if hasattr(self._run_journal, "_store"):
            try:
                from genus.memory.context_builder import build_episodic_context
                from genus.memory.query import query_runs

                store = self._run_journal._store
                header = self._run_journal.get_header()
                repo_id = header.repo_id if header else None

                past_headers = query_runs(store, repo_id=repo_id, limit=10)
                past_run_ids = [h.run_id for h in past_headers if h.run_id != run_id]

                if past_run_ids:
                    episodic_context = build_episodic_context(
                        store, run_ids=past_run_ids, max_runs=3
                    )
            except Exception as exc:  # pragma: no cover
                logger.warning("episodic context load failed: %s", exc)

        return RunContext(
            run_id=run_id,
            goal=goal,
            bus=self._bus,
            journal=self._run_journal,
            sender_id=self._sender_id,
            timeouts=timeouts,
            strategy_selector=self._strategy_selector,
            episodic_context=episodic_context,
            context=context,
        )

    def _journal_event(self, ctx: RunContext, phase: str, event_type: str, summary: str, **kwargs: Any) -> None:
        """Write a journal event, swallowing errors gracefully.

        Args:
            ctx:        The shared RunContext.
            phase:      Phase name (e.g. "loop", "test").
            event_type: Event type string.
            summary:    Human-readable summary.
            **kwargs:   Additional keyword arguments forwarded to log_event.
        """
        try:
            ctx.journal.log_event(phase=phase, event_type=event_type, summary=summary, **kwargs)
        except Exception as exc:  # pragma: no cover
            logger.warning("journal write failed (%s/%s): %s", phase, event_type, exc)

    # ------------------------------------------------------------------
    # Public async entrypoint
    # ------------------------------------------------------------------

    async def run(
        self,
        run_id: str,
        goal: str,
        requirements: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute the full dev-loop.

        Sequences PlanPhaseRunner → ImplPhaseRunner → [TestPhaseRunner →
        FixPhaseRunner]* → ReviewPhaseRunner, then applies the Ask/Stop policy.

        Args:
            run_id:       Unique run identifier for this loop.
            goal:         Human-readable goal/objective.
            requirements: Optional list of acceptance requirements.
            constraints:  Optional list of constraints.
            context:      Optional context dict (e.g. repo, branch).

        Raises:
            DevResponseFailedError:  If any phase fails.
            DevResponseTimeoutError: If any phase times out.
        """
        ctx = self._build_context(run_id, goal, context=context)

        try:
            # -- Loop started --
            await self._bus.publish(
                events.dev_loop_started_message(
                    run_id, self._sender_id, goal, context=context
                )
            )
            self._journal_event(
                ctx, "loop", "started",
                summary=f"Dev loop started: {goal}",
                data={"goal": goal, "context": context or {}},
            )

            # -- Plan --
            try:
                plan = await PlanPhaseRunner().run(
                    ctx, requirements=requirements, constraints=constraints
                )
            except ValueError as exc:
                # Empty plan — PlanPhaseRunner raises ValueError
                reason = str(exc)
                await self._bus.publish(
                    events.dev_loop_failed_message(run_id, self._sender_id, reason)
                )
                self._journal_event(ctx, "loop", "failed", summary=reason)
                return

            # -- Implement --
            await ImplPhaseRunner().run(ctx, plan=plan, iteration=0)

            # -- Test → Fix loop --
            iteration = 0
            while iteration <= self._max_iterations:
                test_report, tests_passed = await TestPhaseRunner().run(ctx, iteration=iteration)

                if tests_passed:
                    break

                if iteration >= self._max_iterations:
                    reason = (
                        f"Max iterations ({self._max_iterations}) reached. "
                        f"Tests still failing: {test_report.get('summary', 'unknown')}"
                    )
                    await self._bus.publish(
                        events.dev_loop_failed_message(run_id, self._sender_id, reason)
                    )
                    self._journal_event(ctx, "loop", "failed", summary=reason)
                    return

                iteration += 1
                await FixPhaseRunner().run(ctx, test_report=test_report, iteration=iteration)

            # -- Review --
            review = await ReviewPhaseRunner().run(ctx)

            # -- Ask/Stop policy --
            ask, reason = should_ask_user(
                findings=review.get("findings", []),
                risks=plan.get("risks", []),
                scope_change=False,
                security_impact=False,
            )
            if ask:
                fail_reason = f"Awaiting operator: {reason}"
                await self._bus.publish(
                    events.dev_loop_failed_message(run_id, self._sender_id, fail_reason)
                )
                self._journal_event(ctx, "loop", "failed", summary=fail_reason)
                return

            # -- Completed --
            await self._bus.publish(
                events.dev_loop_completed_message(
                    run_id, self._sender_id, summary="Dev loop completed successfully."
                )
            )
            self._journal_event(ctx, "loop", "completed", summary="Dev loop completed successfully.")

        except (DevResponseFailedError, DevResponseTimeoutError) as exc:
            await self._bus.publish(
                events.dev_loop_failed_message(run_id, self._sender_id, str(exc))
            )
            try:
                ctx.journal.log_event(
                    phase="loop", event_type="failed", summary=str(exc)
                )
            except Exception as journal_exc:  # pragma: no cover
                logger.error(
                    "journal write failed during loop failure handling: %s", journal_exc
                )
            raise
