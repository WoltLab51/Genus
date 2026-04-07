"""
GENUS API Lifespan

Manages startup and shutdown of all system components:
- MessageBus
- KillSwitch (shared instance wired into both API state and MessageBus)
- DevLoop agents (PlannerAgent, BuilderAgent, TesterAgent, ReviewerAgent)
- EvaluationAgent, StrategyLearningAgent, FeedbackAgent

Design:
- Single shared KillSwitch instance — same object in app.state AND MessageBus
- All agents started in lifespan, stopped on shutdown
- DevLoop trigger: subscribes to run.started → starts DevLoopOrchestrator.run() as asyncio.Task
- RunJournal created per-run (not shared)
"""

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from fastapi import FastAPI

from genus.communication.message_bus import Message, MessageBus
from genus.run.topics import RUN_STARTED
from genus.security.kill_switch import KillSwitch

logger = logging.getLogger(__name__)


@asynccontextmanager
async def genus_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context: start all agents, wire DevLoop trigger, stop on shutdown."""

    # 1. Create shared KillSwitch — same instance for API state AND MessageBus
    ks = KillSwitch()

    # 2. Create MessageBus with KillSwitch wired in
    bus = MessageBus(kill_switch=ks)

    # 3. Store in app state (so deps.py can inject them)
    app.state.message_bus = bus
    app.state.kill_switch = ks

    # 4. Start pipeline agents
    agents = await _start_agents(bus)

    # 5. Subscribe to run.started → trigger DevLoopOrchestrator
    async def _on_run_started(msg: Message) -> None:
        run_id = msg.metadata.get("run_id") or msg.payload.get("run_id")
        goal = msg.payload.get("goal", "")
        if not run_id:
            logger.warning("run.started received without run_id — ignored")
            return
        logger.info("Starting DevLoop for run_id=%s goal=%r", run_id, goal)
        asyncio.create_task(_run_devloop(bus, ks, run_id, goal))

    bus.subscribe(RUN_STARTED, "lifespan:run.started", _on_run_started)

    logger.info("GENUS API started — all agents active")

    yield  # API is running

    # Shutdown
    for agent in agents:
        try:
            stop_result = agent.stop()
            if inspect.isawaitable(stop_result):
                await stop_result
        except Exception as exc:
            logger.warning("Agent stop failed: %s", exc)

    logger.info("GENUS API shutdown complete")


async def _run_devloop(bus: MessageBus, ks: KillSwitch, run_id: str, goal: str) -> None:
    """Run DevLoopOrchestrator for a single run. Called as asyncio.Task."""
    from genus.dev.devloop_orchestrator import DevLoopOrchestrator
    from genus.dev.agents.planner_agent import PlannerAgent
    from genus.dev.agents.builder_agent import BuilderAgent
    from genus.dev.agents.tester_agent import TesterAgent
    from genus.dev.agents.reviewer_agent import ReviewerAgent
    from genus.memory.run_journal import RunJournal
    from genus.memory.store_jsonl import JsonlRunStore

    # Per-run journal (not shared between runs)
    store = JsonlRunStore()
    journal = RunJournal(run_id, store)

    # Per-run agents (subscribe/unsubscribe cleanly)
    planner = PlannerAgent(bus)
    builder = BuilderAgent(bus)
    tester = TesterAgent(bus)
    reviewer = ReviewerAgent(bus)

    run_agents = [planner, builder, tester, reviewer]
    for agent in run_agents:
        agent.start()

    try:
        orchestrator = DevLoopOrchestrator(
            bus=bus,
            run_journal=journal,
            timeout_s=60.0,
            max_iterations=3,
        )
        await orchestrator.run(run_id=run_id, goal=goal)
    except Exception as exc:
        logger.error("DevLoop failed for run_id=%s: %s", run_id, exc)
    finally:
        for agent in run_agents:
            try:
                agent.stop()
            except Exception as exc:
                logger.warning("Agent stop failed: %s", exc)


async def _start_agents(bus: MessageBus) -> List[object]:
    """Instantiate and start global pipeline agents (EvaluationAgent, StrategyLearningAgent, FeedbackAgent).

    Returns list of started agents for shutdown.
    """
    agents = []  # type: List[object]

    try:
        from genus.meta.agents.evaluation_agent import EvaluationAgent
        agent = EvaluationAgent(bus)
        agent.start()
        agents.append(agent)
    except ImportError:
        logger.warning("EvaluationAgent not available — skipping")

    try:
        from genus.strategy.agents.learning_agent import StrategyLearningAgent
        agent = StrategyLearningAgent(bus)
        agent.start()
        agents.append(agent)
    except ImportError:
        logger.warning("StrategyLearningAgent not available — skipping")

    try:
        from genus.feedback.agent import FeedbackAgent
        from genus.memory.run_journal import RunJournal
        from genus.memory.store_jsonl import JsonlRunStore

        def _journal_factory(run_id: str):
            return RunJournal(run_id, JsonlRunStore())

        agent = FeedbackAgent(bus, journal_factory=_journal_factory)
        await agent.initialize()
        await agent.start()
        agents.append(agent)
    except ImportError:
        logger.warning("FeedbackAgent not available — skipping")

    return agents
