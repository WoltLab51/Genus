"""
POST /runs

Auth: Operator (Bearer token)
Body: {"goal": str, "run_id": str (optional)}
Action: publishes run.started on MessageBus
Response: {"run_id": str, "status": "started"}

IMPORTANT: No direct system interaction.
Only publish("run.started", payload) on the bus.
The system reacts on its own.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from genus.api.deps import get_message_bus, verify_operator
from genus.communication.message_bus import Message
from genus.core.run import new_run_id
from genus.run.topics import RUN_STARTED

router = APIRouter()


class StartRunRequest(BaseModel):
    goal: str
    run_id: Optional[str] = None


@router.post("")
async def start_run(
    body: StartRunRequest,
    _: None = Depends(verify_operator),
    bus=Depends(get_message_bus),
) -> JSONResponse:
    """Start a new run by publishing run.started on the MessageBus."""
    run_id = body.run_id or new_run_id(slug=body.goal)

    msg = Message(
        topic=RUN_STARTED,
        payload={"goal": body.goal, "run_id": run_id},
        sender_id="api",
        metadata={"run_id": run_id},
    )

    if bus is not None:
        await bus.publish(msg)

    return JSONResponse({"run_id": run_id, "status": "started"})
