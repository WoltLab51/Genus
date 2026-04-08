"""
POST /runs — Start a new run
GET  /runs/{run_id} — Get the current status of a run
GET  /runs/{run_id}/ws — Stream live run events over WebSocket

Auth: Operator (Bearer token)

POST body: {"goal": str, "run_id": str (optional)}
POST action: publishes run.started on MessageBus
POST response: {"run_id": str, "status": "started"}

GET response: RunStatusResponse (200) or {"detail": "Run '...' not found"} (404)

WebSocket: Auth via ?token= query parameter (Bearer header not available in WS).
           Streams MessageBus events for the given run_id in real time.

IMPORTANT: No direct system interaction in POST.
Only publish("run.started", payload) on the bus.
The system reacts on its own.
"""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from genus.api.deps import get_message_bus, get_run_store, verify_operator
from genus.communication.message_bus import Message
from genus.core.run import new_run_id
from genus.dev.topics import DEV_LOOP_COMPLETED, DEV_LOOP_FAILED, DEV_LOOP_STARTED
from genus.feedback.topics import FEEDBACK_RECEIVED
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore
from genus.meta.topics import META_EVALUATION_COMPLETED
from genus.run.topics import RUN_STARTED

router = APIRouter()

# Topics to watch for WebSocket live-status streaming
WATCH_TOPICS = [
    DEV_LOOP_STARTED,
    DEV_LOOP_COMPLETED,
    DEV_LOOP_FAILED,
    META_EVALUATION_COMPLETED,
    FEEDBACK_RECEIVED,
]

# Topics that signal the end of a run
_TERMINAL_TOPICS = {DEV_LOOP_COMPLETED, DEV_LOOP_FAILED}

_WS_TIMEOUT_SECONDS = 300  # 5 minutes
_WS_KEEPALIVE_SECONDS = 30.0  # interval between keepalive pings


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


@router.websocket("/{run_id}/ws")
async def run_status_ws(
    run_id: str,
    websocket: WebSocket,
    token: Optional[str] = None,
) -> None:
    """Stream live run events over WebSocket.

    Auth: Bearer token via ``?token=`` query parameter.
    Sends a ``{"type": "connected", "run_id": ...}`` message on connect,
    then relays matching MessageBus events until a terminal event arrives or
    the 5-minute timeout expires.
    """
    await websocket.accept()

    # 1. Auth check
    app = websocket.app
    expected_key = getattr(app.state, "api_key", None)
    if not token or token != expected_key:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close(code=1008)
        return

    # 2. Check run exists
    run_store = getattr(app.state, "run_store", None)
    if run_store is None:
        run_store = JsonlRunStore()
    journal = RunJournal(run_id, run_store)
    if not journal.exists():
        await websocket.send_json({"type": "error", "message": f"Run '{run_id}' not found"})
        await websocket.close(code=1008)
        return

    # 3. Get MessageBus
    bus = getattr(app.state, "message_bus", None)
    if bus is None:
        await websocket.send_json({"type": "error", "message": "MessageBus not available"})
        await websocket.close()
        return

    # 4. Subscribe to bus topics
    queue: asyncio.Queue = asyncio.Queue()
    subscriber_id = f"ws:{run_id}:{id(websocket)}"
    loop = asyncio.get_running_loop()

    def _on_event(msg: Message) -> None:
        msg_run_id = msg.metadata.get("run_id") or msg.payload.get("run_id", "")
        if msg_run_id == run_id:
            loop.call_soon_threadsafe(queue.put_nowait, msg)

    for topic in WATCH_TOPICS:
        bus.subscribe(topic, subscriber_id, _on_event)

    # 5. Send initial connected message
    await websocket.send_json({"type": "connected", "run_id": run_id})

    try:
        deadline = loop.time() + _WS_TIMEOUT_SECONDS

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                await websocket.send_json({"type": "timeout", "run_id": run_id})
                break

            try:
                msg = await asyncio.wait_for(queue.get(), timeout=min(remaining, _WS_KEEPALIVE_SECONDS))
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
                continue

            await websocket.send_json({
                "type": "event",
                "topic": msg.topic,
                "run_id": run_id,
                "payload": msg.payload,
            })

            if msg.topic in _TERMINAL_TOPICS:
                break

    except WebSocketDisconnect:
        pass  # Client disconnected — normal

    finally:
        bus.unsubscribe_all(subscriber_id)
        try:
            await websocket.close()
        except Exception:
            pass
