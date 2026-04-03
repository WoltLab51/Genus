import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.logger import get_logger
from core.messaging import event_bus
from core.memory import memory_store
from agents.data_collector.router import router as data_collector_router
from agents.analysis.router import router as analysis_router
from agents.decision.router import router as decision_router

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GENUS system starting...")
    yield
    logger.info("GENUS system shutting down...")


app = FastAPI(
    title="GENUS API",
    description="Modular AI System - Multi-Agent API",
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

app.include_router(data_collector_router)
app.include_router(analysis_router)
app.include_router(decision_router)


@app.get("/")
async def root():
    return {"system": "GENUS", "version": "0.1.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/system/status")
async def system_status():
    from agents.data_collector.agent import data_collector_agent
    from agents.analysis.agent import analysis_agent
    from agents.decision.agent import decision_agent

    return {
        "system": "GENUS",
        "agents": [
            data_collector_agent.get_status(),
            analysis_agent.get_status(),
            decision_agent.get_status(),
        ],
    }


@app.get("/system/events")
async def system_events(limit: int = 50):
    return {"events": event_bus.event_log(limit)}


@app.get("/system/memory")
async def system_memory(namespace: str = ""):
    if namespace:
        return {"namespace": namespace, "data": memory_store.get_all(namespace)}
    return {"history": memory_store.history()}


@app.post("/system/pipeline/run")
async def run_pipeline():
    """Run the full data collection -> analysis -> decision pipeline."""
    from agents.data_collector.agent import data_collector_agent

    logger.info("Running full pipeline")
    items = await data_collector_agent.run()
    return {
        "status": "pipeline_complete",
        "collected_items": len(items),
        "message": "Pipeline triggered. Analysis and Decision agents respond via event bus.",
    }
