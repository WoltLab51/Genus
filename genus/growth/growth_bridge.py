"""
Growth Bridge

Bridges the GrowthOrchestrator and the DevLoopOrchestrator.  When the
GrowthOrchestrator approves a build it publishes ``growth.build.requested``.
The GrowthBridge is the adapter that translates this event into a
:class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator` run.

Position in the GENUS growth flow::

    NeedObserver → GrowthOrchestrator
        → GrowthBridge  (this module)
            → DevLoopOrchestrator
                → AgentBootstrapper

Each ``growth.build.requested`` event spawns:
  - A dedicated :class:`~genus.memory.run_journal.RunJournal` stored under
    ``<journal_base_path>/<run_id>/``.
  - A fresh :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator`
    instance that owns the entire run.
  - An ``asyncio.Task`` (fire-and-forget) that drives the orchestrator.

**Payload enrichment via one-shot listener:**

The :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator` publishes
``dev.loop.completed`` when it finishes, but that payload only contains a
``summary`` field.  The
:class:`~genus.growth.bootstrapper.AgentBootstrapper` needs ``agent_name``,
``agent_id``, and ``domain`` to perform the bootstrap.

To avoid modifying the DevLoopOrchestrator, GrowthBridge registers a
*one-shot* listener on ``dev.loop.completed`` (scoped per ``run_id``).
When the matching event arrives the listener:

1. Enriches the payload with ``agent_name``, ``agent_id``, and ``domain``
   derived from the original ``growth.build.requested`` payload.
2. Re-publishes ``dev.loop.completed`` with the enriched payload so that
   AgentBootstrapper receives all required fields.
3. Immediately unsubscribes itself to prevent infinite loops and clean up.

Phase 7 will replace this bridge with a real LLM-backed builder agent.

Topics subscribed:
    - ``growth.build.requested``

Topics published:
    - ``growth.loop.started`` — emitted after the DevLoop task is created.
    - ``dev.loop.completed``  — re-published with enriched agent metadata.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.core.run import new_run_id
from genus.dev.devloop_orchestrator import DevLoopOrchestrator
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

if TYPE_CHECKING:
    from genus.llm.router import LLMRouter

logger = logging.getLogger(__name__)

_TOPIC_BUILD_REQUESTED = "growth.build.requested"
_TOPIC_LOOP_STARTED = "growth.loop.started"
_TOPIC_DEV_LOOP_COMPLETED = "dev.loop.completed"


class GrowthBridge(Agent):
    """Adapter between GrowthOrchestrator and DevLoopOrchestrator.

    Listens for ``growth.build.requested`` events and starts a
    :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator` run for
    each approved build.  After the loop completes the bridge enriches the
    ``dev.loop.completed`` payload with agent metadata so that
    :class:`~genus.growth.bootstrapper.AgentBootstrapper` can integrate the
    new agent.

    Args:
        message_bus:       The shared :class:`~genus.communication.message_bus.MessageBus`.
        agent_id:          Optional custom agent ID.  Auto-generated if omitted.
        name:              Optional human-readable agent name.  Defaults to
                           ``"GrowthBridge"``.
        devloop_timeout_s: Per-phase timeout (seconds) passed to the
                           :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator`.
                           Defaults to ``60.0``.
        max_iterations:    Maximum fix iterations passed to the orchestrator.
                           Defaults to ``2``.
        journal_base_path: Root directory under which per-run journals are
                           created.  Defaults to
                           ``~/.genus/growth_runs``.  Override in tests via
                           ``tmp_path``.
        llm_router:        Optional :class:`~genus.llm.router.LLMRouter`.  When
                           provided, the LLM router is injected into each
                           :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator`
                           spawned by this bridge.  When ``None`` (default),
                           orchestrators run in stub mode (backward compatible).
    """

    def __init__(
        self,
        message_bus: MessageBus,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        devloop_timeout_s: float = 60.0,
        max_iterations: int = 2,
        journal_base_path: Optional[Path] = None,
        llm_router: "Optional[LLMRouter]" = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "GrowthBridge")
        self._bus = message_bus
        self._devloop_timeout_s = devloop_timeout_s
        self._max_iterations = max_iterations
        self._journal_base_path: Path = journal_base_path or (
            Path.home() / ".genus" / "growth_runs"
        )
        self._llm_router = llm_router
        # run_id → {"agent_spec_template": {...}, "need_id": str, "domain": str}
        self._active_runs: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to ``growth.build.requested``."""
        self._bus.subscribe(_TOPIC_BUILD_REQUESTED, self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Transition to RUNNING state."""
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Unsubscribe from all topics and transition to STOPPED state."""
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Handle a ``growth.build.requested`` event.

        Extracts the build context from the payload, spins up a
        :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator` as a
        fire-and-forget ``asyncio.Task``, and publishes
        ``growth.loop.started``.

        Missing required fields (``need_id``, ``domain``,
        ``need_description``) are handled gracefully: a warning is logged
        and the message is silently dropped.

        Args:
            message: The incoming ``growth.build.requested`` event.
        """
        if message.topic != _TOPIC_BUILD_REQUESTED:
            return

        payload = message.payload if isinstance(message.payload, dict) else {}
        need_id: str = payload.get("need_id", "")
        domain: str = payload.get("domain", "")
        need_description: str = payload.get("need_description", "")

        if not need_id or not domain or not need_description:
            logger.warning(
                "GrowthBridge: missing required fields in growth.build.requested "
                "(need_id=%r, domain=%r, need_description=%r) — ignoring",
                need_id,
                domain,
                need_description,
            )
            return

        agent_spec_template: dict = dict(payload.get("agent_spec_template") or {})

        run_id = new_run_id(slug=need_description)
        goal = f"{need_description} — Domain: {domain}"

        self._active_runs[run_id] = {
            "agent_spec_template": agent_spec_template,
            "need_id": need_id,
            "domain": domain,
        }

        # Register a one-shot listener that enriches the dev.loop.completed
        # payload once the DevLoop for *this* run_id finishes.
        self._register_completion_listener(run_id, domain, agent_spec_template)

        # Build the journal for this run
        journal = self._make_journal(run_id, goal)

        # Build the orchestrator
        orchestrator = DevLoopOrchestrator(
            bus=self._bus,
            sender_id=self.id,
            timeout_s=self._devloop_timeout_s,
            max_iterations=self._max_iterations,
            run_journal=journal,
            llm_router=self._llm_router,
        )

        # Fire-and-forget — errors are logged; the orchestrator itself
        # publishes dev.loop.failed on error.
        task = asyncio.ensure_future(
            self._run_devloop(run_id, goal, orchestrator)
        )
        task.add_done_callback(self._on_devloop_task_done)

        # Signal that the loop has started
        await self._bus.publish(
            Message(
                topic=_TOPIC_LOOP_STARTED,
                payload={
                    "run_id": run_id,
                    "need_id": need_id,
                    "domain": domain,
                    "goal": goal,
                },
                sender_id=self.id,
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_journal(self, run_id: str, goal: str) -> RunJournal:
        """Create and initialise a :class:`~genus.memory.run_journal.RunJournal`.

        Args:
            run_id: The run identifier.
            goal:   Human-readable goal string written into the journal header.

        Returns:
            An initialised :class:`~genus.memory.run_journal.RunJournal`.
        """
        self._journal_base_path.mkdir(parents=True, exist_ok=True)
        store = JsonlRunStore(base_dir=self._journal_base_path)
        journal = RunJournal(run_id=run_id, store=store)
        journal.initialize(goal=goal)
        return journal

    def _register_completion_listener(
        self,
        run_id: str,
        domain: str,
        agent_spec_template: dict,
    ) -> None:
        """Register a one-shot ``dev.loop.completed`` listener for *run_id*.

        The listener filters by ``run_id``, enriches the payload, re-publishes
        the message, then immediately unsubscribes itself to prevent infinite
        loops.

        Args:
            run_id:              The run identifier to filter on.
            domain:              Domain string used as fallback for agent_name.
            agent_spec_template: Template dict from the original build request.
        """
        subscriber_id = f"{self.id}:run:{run_id}"

        async def _on_loop_completed(msg: Message) -> None:
            # Only handle the event for our run_id
            if msg.metadata.get("run_id") != run_id:
                return

            # Unsubscribe immediately — one-shot
            self._bus.unsubscribe(_TOPIC_DEV_LOOP_COMPLETED, subscriber_id)

            # Enrich the payload with agent metadata
            enriched = dict(msg.payload)
            tpl = self._active_runs.get(run_id, {}).get("agent_spec_template", {})
            enriched["agent_name"] = tpl.get("name", f"{domain.title()}Agent")
            enriched["agent_id"] = run_id
            enriched["domain"] = domain

            # Clean up active run tracking
            self._active_runs.pop(run_id, None)

            # Re-publish with enriched payload so AgentBootstrapper sees it
            await self._bus.publish(
                Message(
                    topic=_TOPIC_DEV_LOOP_COMPLETED,
                    payload=enriched,
                    sender_id=self.id,
                    metadata=dict(msg.metadata),
                )
            )

        self._bus.subscribe(_TOPIC_DEV_LOOP_COMPLETED, subscriber_id, _on_loop_completed)

    async def _run_devloop(
        self,
        run_id: str,
        goal: str,
        orchestrator: DevLoopOrchestrator,
    ) -> None:
        """Drive the DevLoopOrchestrator for a single build.

        Errors from the orchestrator are swallowed here; the orchestrator
        already publishes ``dev.loop.failed`` before raising.

        Args:
            run_id:       The run identifier.
            goal:         The human-readable goal.
            orchestrator: The :class:`~genus.dev.devloop_orchestrator.DevLoopOrchestrator`
                          to run.
        """
        run_info = self._active_runs.get(run_id, {})
        context = {
            "agent_spec_template": copy.deepcopy(run_info.get("agent_spec_template") or {}),
            "domain": run_info.get("domain", ""),
            "need_id": run_info.get("need_id", ""),
        }
        try:
            await orchestrator.run(run_id=run_id, goal=goal, context=context)
        except Exception as exc:
            logger.error(
                "GrowthBridge: DevLoop task failed (run_id=%r): %s",
                run_id,
                exc,
            )

    def _on_devloop_task_done(self, task: "asyncio.Task[None]") -> None:
        """Callback invoked when the DevLoop asyncio.Task completes.

        Logs any unexpected exception that slipped past ``_run_devloop``.
        """
        if not task.cancelled() and task.exception():
            logger.error(
                "GrowthBridge: unexpected DevLoop task error: %s",
                task.exception(),
            )
