from fastapi import APIRouter
from .agent import decision_agent

router = APIRouter(prefix="/agents/decision", tags=["Decision"])


@router.get("/status")
async def get_status():
    return decision_agent.get_status()


@router.post("/run")
async def run_agent(payload: dict = {}):
    decision = await decision_agent.run(payload)
    return decision.model_dump()


@router.get("/decisions")
async def get_decisions():
    return {"decisions": decision_agent.get_decisions()}
