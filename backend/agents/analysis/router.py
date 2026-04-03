from fastapi import APIRouter
from .agent import analysis_agent

router = APIRouter(prefix="/agents/analysis", tags=["Analysis"])


@router.get("/status")
async def get_status():
    return analysis_agent.get_status()


@router.post("/run")
async def run_agent(payload: dict = {}):
    result = await analysis_agent.run(payload)
    return result.model_dump()


@router.get("/results")
async def get_results():
    return {"results": analysis_agent.get_results()}
