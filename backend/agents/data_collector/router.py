from fastapi import APIRouter
from models.schemas import DataItem
from .agent import data_collector_agent

router = APIRouter(prefix="/agents/data-collector", tags=["Data Collector"])


@router.get("/status")
async def get_status():
    return data_collector_agent.get_status()


@router.post("/run")
async def run_agent(payload: dict = {}):
    items = await data_collector_agent.run(payload)
    return {"collected": [i.model_dump() for i in items]}


@router.get("/data")
async def get_collected_data():
    return {"items": data_collector_agent.get_collected()}
