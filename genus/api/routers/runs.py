"""
POST /runs — Start a new run
GET  /runs/{run_id} — Get the current status of a run

Auth: Operator (Bearer token)

POST body: {"goal": str, "run_id": str (optional)}
POST action: publishes run.started on MessageBus
POST response: {"run_id": str, "status": "started"}

GET response: RunStatusResponse (200) or {"detail": "Run '...' not found"} (404)

IMPORTANT: No direct system interaction in POST.
Only publish("run.started", payload) on the bus.
The system reacts on its own.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from genus.api.deps import get_message_bus, get_run_store, verify_operator
from genus.communication.message_bus import Message
from genus.core.run import new_run_id
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
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


@router.get("/{run_id}")
async def get_run_status(
    run_id: str,
    _: None = Depends(verify_operator),
    run_store: JsonlRunStore = Depends(get_run_store),
) -> JSONResponse:
    """Get the current status of a run from its RunJournal."""
    journal = RunJournal(run_id, run_store)

    if not journal.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    header = journal.get_header()
    events = journal.get_events()
    artifact_ids = journal.list_artifacts()

    # Determine status from loop events
    loop_events = [e for e in events if e.phase == "loop"]
    completed = any(e.event_type == "completed" for e in loop_events)
    failed = any(e.event_type == "failed" for e in loop_events)
    started = any(e.event_type == "started" for e in loop_events)

    if completed:
        status = "completed"
    elif failed:
        status = "failed"
    elif started:
        status = "running"
    else:
        status = "unknown"

    # Current phase: last event's phase
    current_phase = events[-1].phase if events else None

    # Iterations: count fix_completed events in fix phase
    iterations = sum(
        1 for e in events
        if e.phase == "fix" and e.event_type == "fix_completed"
    )

    return JSONResponse({
        "run_id": run_id,
        "goal": header.goal if header else None,
        "created_at": header.created_at if header else None,
        "repo_id": header.repo_id if header else None,
        "status": status,
        "current_phase": current_phase,
        "iterations": iterations,
        "artifacts_count": len(artifact_ids),
        "events_count": len(events),
    })
