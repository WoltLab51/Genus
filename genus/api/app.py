"""
FastAPI application factory.

``create_app()`` wires everything up: stores, message bus, agents, lifecycle,
and routes.  The lifespan context manager owns initialisation and teardown
so there are **no module-level singletons**.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from genus.core.config import Config
from genus.core.lifecycle import Lifecycle
from genus.communication.message_bus import MessageBus
from genus.storage.store import DecisionStore, FeedbackStore
from genus.storage.memory import MemoryStore
from genus.agents.data_collector import DataCollectorAgent
from genus.agents.analysis import AnalysisAgent
from genus.agents.decision import DecisionAgent

from .schemas import (
    AgentStatusResponse,
    DecisionCreate,
    DecisionResponse,
    DecisionWithFeedback,
    FeedbackCreate,
    FeedbackResponse,
)

logger = logging.getLogger("genus.api")


# ---------------------------------------------------------------------------
#  Application state (populated during lifespan — no globals)
# ---------------------------------------------------------------------------

class _AppState:
    """Mutable bag attached to ``app.state`` during lifespan."""

    config: Config
    bus: MessageBus
    memory: MemoryStore
    decision_store: DecisionStore
    feedback_store: FeedbackStore
    lifecycle: Lifecycle
    # agents
    data_collector: DataCollectorAgent
    analysis: AnalysisAgent
    decision: DecisionAgent


# ---------------------------------------------------------------------------
#  Dependency helpers
# ---------------------------------------------------------------------------

def _state(app: FastAPI) -> _AppState:  # noqa: D401
    return app.state  # type: ignore[return-value]


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------

def create_app(
    database_url: Optional[str] = None,
    config: Optional[Config] = None,
) -> FastAPI:
    """Build and return a fully-wired FastAPI application."""

    cfg = config or Config()
    db_url = database_url or cfg.get("database.url", "sqlite+aiosqlite:///./genus.db")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s: _AppState = app.state  # type: ignore[assignment]

        # --- infrastructure ---
        s.config = cfg
        s.bus = MessageBus(max_history=cfg.get("message_bus.max_history", 1000))
        s.memory = MemoryStore()
        s.decision_store = DecisionStore(db_url)
        s.feedback_store = FeedbackStore(db_url)

        await s.decision_store.init_db()
        await s.feedback_store.init_db()

        # --- agents ---
        s.data_collector = DataCollectorAgent(s.bus, s.memory)
        s.analysis = AnalysisAgent(s.bus, s.memory)
        s.decision = DecisionAgent(s.bus, s.memory)

        s.lifecycle = Lifecycle()
        s.lifecycle.register(s.data_collector)
        s.lifecycle.register(s.analysis)
        s.lifecycle.register(s.decision)
        await s.lifecycle.start_all()

        logger.info("GENUS system started")
        yield

        await s.lifecycle.stop_all()
        await s.decision_store.close()
        await s.feedback_store.close()
        logger.info("GENUS system shut down")

    app = FastAPI(
        title="GENUS API",
        description="Unified Modular Multi-Agent System",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- route registration ---
    _register_system_routes(app)
    _register_agent_routes(app)
    _register_decision_routes(app)
    _register_feedback_routes(app)
    _register_event_routes(app)

    return app


# ---------------------------------------------------------------------------
#  Routes
# ---------------------------------------------------------------------------

def _register_system_routes(app: FastAPI) -> None:
    @app.get("/")
    async def root():
        return {"system": "GENUS", "version": "0.1.0", "status": "running"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/system/status")
    async def system_status():
        s = _state(app)
        return {
            "system": "GENUS",
            "agents": [
                s.data_collector.get_status(),
                s.analysis.get_status(),
                s.decision.get_status(),
            ],
        }

    @app.get("/system/memory")
    async def system_memory(namespace: str = ""):
        s = _state(app)
        if namespace:
            return {"namespace": namespace, "data": s.memory.get_all(namespace)}
        return {"history": s.memory.history()}

    @app.post("/system/pipeline/run")
    async def run_pipeline():
        s = _state(app)
        items = await s.data_collector.execute()
        return {
            "status": "pipeline_complete",
            "collected_items": len(items),
            "message": "Pipeline triggered.  Analysis and Decision agents respond via event bus.",
        }


def _register_agent_routes(app: FastAPI) -> None:
    @app.get("/agents/data-collector/status")
    async def dc_status():
        return _state(app).data_collector.get_status()

    @app.post("/agents/data-collector/run")
    async def dc_run(payload: dict = {}):
        items = await _state(app).data_collector.execute(payload)
        return {"collected": items}

    @app.get("/agents/data-collector/data")
    async def dc_data():
        return {"items": _state(app).data_collector.get_collected()}

    @app.get("/agents/analysis/status")
    async def analysis_status():
        return _state(app).analysis.get_status()

    @app.post("/agents/analysis/run")
    async def analysis_run(payload: dict = {}):
        return await _state(app).analysis.execute(payload)

    @app.get("/agents/analysis/results")
    async def analysis_results():
        return {"results": _state(app).analysis.get_results()}

    @app.get("/agents/decision/status")
    async def decision_status():
        return _state(app).decision.get_status()

    @app.post("/agents/decision/run")
    async def decision_run(payload: dict = {}):
        return await _state(app).decision.execute(payload)

    @app.get("/agents/decision/decisions")
    async def decision_decisions():
        return {"decisions": _state(app).decision.get_decisions()}


def _register_decision_routes(app: FastAPI) -> None:
    @app.post("/decisions", response_model=DecisionResponse, status_code=201)
    async def create_decision(body: DecisionCreate):
        s = _state(app)
        did = await s.decision_store.store(
            agent_id=body.agent_id,
            decision_type=body.decision_type,
            input_data=body.input_data,
            output_data=body.output_data,
            metadata=body.metadata,
        )
        await s.bus.publish_event(
            "decision.created",
            {"decision_id": did, "agent_id": body.agent_id},
            sender="api",
        )
        row = await s.decision_store.get(did)
        return DecisionResponse.model_validate(row)

    @app.get("/decisions", response_model=List[DecisionResponse])
    async def list_decisions(
        agent_id: Optional[str] = None,
        decision_type: Optional[str] = None,
        limit: int = 100,
    ):
        rows = await _state(app).decision_store.list(
            agent_id=agent_id,
            decision_type=decision_type,
            limit=limit,
        )
        return [DecisionResponse.model_validate(r) for r in rows]

    @app.get("/decisions/{decision_id}", response_model=DecisionWithFeedback)
    async def get_decision(decision_id: str):
        s = _state(app)
        row = await s.decision_store.get(decision_id)
        if not row:
            raise HTTPException(404, "Decision not found")
        feedbacks = await s.feedback_store.list_for_decision(decision_id)
        d = DecisionResponse.model_validate(row).model_dump()
        d["feedbacks"] = [FeedbackResponse.model_validate(f) for f in feedbacks]
        return DecisionWithFeedback(**d)


def _register_feedback_routes(app: FastAPI) -> None:
    @app.post("/feedback", response_model=FeedbackResponse, status_code=201)
    async def create_feedback(body: FeedbackCreate):
        s = _state(app)
        decision = await s.decision_store.get(body.decision_id)
        if not decision:
            raise HTTPException(404, "Decision not found")
        fid = await s.feedback_store.store(
            decision_id=body.decision_id,
            score=body.score,
            label=body.label,
            notes=body.notes,
            source=body.source,
        )
        await s.bus.publish_event(
            "decision.feedback",
            {"feedback_id": fid, "decision_id": body.decision_id, "score": body.score},
            sender="api",
        )
        row = await s.feedback_store.get(fid)
        return FeedbackResponse.model_validate(row)

    @app.get("/feedback", response_model=List[FeedbackResponse])
    async def list_feedback(label: Optional[str] = None, limit: int = 100):
        rows = await _state(app).feedback_store.list_all(label=label, limit=limit)
        return [FeedbackResponse.model_validate(r) for r in rows]

    @app.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
    async def get_feedback(feedback_id: str):
        row = await _state(app).feedback_store.get(feedback_id)
        if not row:
            raise HTTPException(404, "Feedback not found")
        return FeedbackResponse.model_validate(row)


def _register_event_routes(app: FastAPI) -> None:
    @app.get("/system/events")
    async def system_events(topic: Optional[str] = None, limit: int = 50):
        msgs = _state(app).bus.get_history(topic=topic, limit=limit)
        return {"events": [m.to_dict() for m in msgs]}
