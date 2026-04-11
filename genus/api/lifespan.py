"""
GENUS API Lifespan

Manages startup and shutdown of all system components:
- MessageBus
- KillSwitch (shared instance wired into both API state and MessageBus)
- LLMRouter (built from environment variables at startup)
- DevLoop agents (PlannerAgent, BuilderAgent, TesterAgent, ReviewerAgent)
- EvaluationAgent, StrategyLearningAgent, FeedbackAgent

Design:
- Single shared KillSwitch instance — same object in app.state AND MessageBus
- All agents started in lifespan, stopped on shutdown
- DevLoop trigger: subscribes to run.started → starts DevLoopOrchestrator.run() as asyncio.Task
- RunJournal created per-run (not shared)
- LLMRouter built once at startup, injected into per-run agents
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, List, Optional

from fastapi import FastAPI

from genus.communication.message_bus import Message, MessageBus
from genus.run.topics import RUN_STARTED
from genus.security.kill_switch import KillSwitch

if TYPE_CHECKING:
    from genus.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def build_llm_router() -> "Optional[LLMRouter]":
    """Build LLMRouter with all configured providers.

    Reads configuration from environment variables:
    - GENUS_LLM_OLLAMA_URL   (Default: http://localhost:11434)
    - GENUS_LLM_OLLAMA_MODEL (Default: llama3.2)
    - GENUS_OPENAI_API_KEY   (optional: enables OpenAIProvider)
    - GENUS_LLM_STRATEGY     (Default: adaptive)
    - GENUS_LLM_SCORES_PATH  (Default: var/router_scores.jsonl)

    Returns:
        A configured :class:`~genus.llm.router.LLMRouter`, or ``None`` when no
        providers could be registered (graceful degradation — stub mode).

    LLM errors never block API startup.
    """
    try:
        from genus.llm.providers.registry import ProviderRegistry
        from genus.llm.providers.ollama_provider import OllamaProvider
        from genus.llm.router import LLMRouter, RoutingStrategy

        registry = ProviderRegistry()

        # Ollama — always attempted first (runs locally on Pi / dev machine)
        try:
            ollama_url = os.environ.get("GENUS_LLM_OLLAMA_URL", "http://localhost:11434")
            ollama_model = os.environ.get("GENUS_LLM_OLLAMA_MODEL", "llama3.2")
            registry.register(OllamaProvider(base_url=ollama_url, default_model=ollama_model))
            logger.info("OllamaProvider registered: %s (model: %s)", ollama_url, ollama_model)
        except Exception as exc:
            logger.warning("OllamaProvider setup failed: %s", exc)

        # OpenAI — optional, only when API key is set
        openai_key = os.environ.get("GENUS_OPENAI_API_KEY")
        if openai_key:
            try:
                from genus.llm.providers.openai_provider import OpenAIProvider
                from genus.llm.credential_store import CredentialStore

                store = CredentialStore()
                store.set("openai", "api_key", openai_key)
                registry.register(OpenAIProvider(credential_store=store))
                logger.info("OpenAIProvider registered")
            except Exception as exc:
                logger.warning("OpenAIProvider setup failed: %s", exc)

        if not registry.list():
            logger.warning("No LLM providers configured — DevLoop runs in stub mode")
            return None

        strategy_name = os.environ.get("GENUS_LLM_STRATEGY", "adaptive").upper()
        strategy = (
            RoutingStrategy[strategy_name]
            if strategy_name in RoutingStrategy.__members__
            else RoutingStrategy.ADAPTIVE
        )

        scores_path = Path(
            os.environ.get("GENUS_LLM_SCORES_PATH", "var/router_scores.jsonl")
        )
        scores_path.parent.mkdir(parents=True, exist_ok=True)

        router = LLMRouter(registry=registry, strategy=strategy, scores_path=scores_path)
        logger.info(
            "LLMRouter ready (strategy=%s, providers=%s)",
            strategy.value,
            [p.name for p in registry.list()],
        )
        return router

    except Exception as exc:
        logger.warning("LLMRouter build failed — running in stub mode: %s", exc)
        return None


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

    # 4. Build LLMRouter from environment variables (graceful degradation if unavailable)
    llm_router = await build_llm_router()

    # Store LLMRouter in app state (needed by WebSocket handler)
    app.state.llm_router = llm_router

    # 5. Start pipeline agents
    agents = await _start_agents(bus)

    # 6. Start ConversationAgent + ConnectionManager
    from genus.conversation.conversation_agent import ConversationAgent
    from genus.api.connection_manager import ConnectionManager

    conversations_dir = Path(
        os.environ.get("GENUS_CONVERSATIONS_DIR", "var/conversations")
    )
    conversations_dir.mkdir(parents=True, exist_ok=True)
    max_history = int(os.environ.get("GENUS_MAX_CONVERSATION_HISTORY", "20"))
    session_timeout = int(os.environ.get("GENUS_SESSION_TIMEOUT_MINUTES", "30"))

    conversation_agent = ConversationAgent(
        message_bus=bus,
        llm_router=llm_router,
        max_history=max_history,
        conversations_dir=conversations_dir,
    )
    await conversation_agent.initialize()
    await conversation_agent.start()

    connection_manager = ConnectionManager(
        default_llm_router=llm_router,
        default_bus=bus,
        conversations_dir=conversations_dir,
        max_history=max_history,
    )
    app.state.connection_manager = connection_manager
    logger.info("ConversationAgent + ConnectionManager started")

    # 7. Subscribe to run.started → trigger DevLoopOrchestrator
    async def _on_run_started(msg: Message) -> None:
        run_id = msg.metadata.get("run_id") or msg.payload.get("run_id")
        goal = msg.payload.get("goal", "")
        if not run_id:
            logger.warning("run.started received without run_id — ignored")
            return
        logger.info("Starting DevLoop for run_id=%s goal=%r", run_id, goal)
        task = asyncio.create_task(_run_devloop(bus, ks, run_id, goal, llm_router=llm_router))

        def _on_devloop_done(t: "asyncio.Task[None]") -> None:
            if not t.cancelled() and t.exception():
                logger.error(
                    "DevLoop task for run_id=%s raised unexpected exception",
                    run_id,
                    exc_info=t.exception(),
                )

        task.add_done_callback(_on_devloop_done)

    bus.subscribe(RUN_STARTED, "lifespan:run.started", _on_run_started)

    logger.info("GENUS API started — all agents active")

    yield  # API is running

    # Shutdown
    try:
        await conversation_agent.stop()
    except Exception as exc:
        logger.warning("ConversationAgent stop failed: %s", exc)

    for agent in agents:
        try:
            stop_result = agent.stop()
            if asyncio.iscoroutine(stop_result):
                await stop_result
        except Exception as exc:
            logger.warning("Agent stop failed: %s", exc)

    logger.info("GENUS API shutdown complete")


async def _run_devloop(
    bus: MessageBus,
    ks: KillSwitch,
    run_id: str,
    goal: str,
    *,
    llm_router: Optional["LLMRouter"] = None,
) -> None:
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

    # Per-run agents (subscribe/unsubscribe cleanly), with LLMRouter injected
    planner = PlannerAgent(bus, llm_router=llm_router)
    builder = BuilderAgent(bus, llm_router=llm_router)
    tester = TesterAgent(bus)
    reviewer = ReviewerAgent(bus, llm_router=llm_router)

    run_agents = [planner, builder, tester, reviewer]
    for agent in run_agents:
        agent.start()

    try:
        orchestrator = DevLoopOrchestrator(
            bus=bus,
            run_journal=journal,
            timeout_s=60.0,
            max_iterations=3,
            llm_router=llm_router,
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
    """Instantiate and start global pipeline agents (EvaluationAgent, StrategyLearningAgent, FeedbackAgent, NeedObserver).

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

    try:
        from genus.growth.need_observer import NeedObserver
        from genus.growth.need_store import NeedStore
        from genus.growth.code_validator import CodeValidator
        from genus.growth.bootstrapper import AgentBootstrapper
        from genus.communication.topic_registry import TopicRegistry

        needs_dir = Path(os.environ.get("GENUS_NEEDS_DIR", "var/needs"))
        needs_dir.mkdir(parents=True, exist_ok=True)
        need_store = NeedStore(base_dir=needs_dir)

        need_observer = NeedObserver(
            message_bus=bus,
            need_store=need_store,
        )
        await need_observer.initialize()
        await need_observer.start()
        agents.append(need_observer)

        # AgentBootstrapper with code validator + optional sandbox runner (Phase 11c)
        code_validator = CodeValidator()
        sandbox_enabled = (
            os.environ.get("GENUS_SANDBOX_ENABLED", "true").lower() == "true"
        )
        # Any truthy object enables the sandbox import-check; the check itself
        # uses asyncio.create_subprocess_exec internally (no workspace needed).
        sandbox_runner = object() if sandbox_enabled else None

        topic_registry = TopicRegistry()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=topic_registry,
            code_validator=code_validator,
            sandbox_runner=sandbox_runner,
        )
        await bootstrapper.initialize()
        await bootstrapper.start()
        agents.append(bootstrapper)
        logger.info(
            "AgentBootstrapper started (sandbox_enabled=%s)", sandbox_enabled
        )
    except ImportError:
        logger.warning("NeedObserver / AgentBootstrapper not available — skipping")

    return agents
