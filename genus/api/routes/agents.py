"""Functional Agents API — GENUS-2.0

Endpoints:
  GET  /v1/agents/                    → list all registered functional agents
  GET  /v1/agents/{agent_id}/status   → single agent status
  POST /v1/agents/{agent_id}/invoke   → invoke agent with an intent string
  WS   /v1/agents/{agent_id}/stream   → live streaming over WebSocket

Auth: standard ``Authorization: Bearer <key>`` header (HTTP) or
      ``?token=<key>`` query parameter (WebSocket).

WebSocket protocol (JSON):

Client → Server::

    {"type": "invoke", "intent": "...", "user_id": "...", "session_id": "..."}
    {"type": "ping"}

Server → Client::

    {"type": "thinking", "agent_id": "..."}
    {"type": "response", "agent_id": "...", "text": "...", "success": true, "data": null}
    {"type": "pong"}
    {"type": "error",    "message": "..."}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from genus.api.deps import verify_reader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_registry(request: Request):
    """Return the FunctionalAgentRegistry from app state, or raise 503."""
    registry = getattr(request.app.state, "functional_agent_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail="Functional agent registry not available",
        )
    return registry


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    intent: str
    user_id: Optional[str] = None
    session_id: str = "default"
    metadata: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


@router.get("/v1/agents/")
async def list_agents(
    request: Request,
    _: None = Depends(verify_reader),
) -> list:
    """Return status dicts for all registered functional agents."""
    registry = _get_registry(request)
    return [agent.status() for agent in registry.list_all()]


@router.get("/v1/agents/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
    request: Request,
    _: None = Depends(verify_reader),
) -> Dict[str, Any]:
    """Return the status of a single functional agent.

    Raises:
        HTTPException 404: When no agent with *agent_id* is registered.
    """
    registry = _get_registry(request)
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent.status()


@router.post("/v1/agents/{agent_id}/invoke")
async def invoke_agent(
    agent_id: str,
    body: InvokeRequest,
    request: Request,
    _: None = Depends(verify_reader),
) -> Dict[str, Any]:
    """Invoke a functional agent with an intent string.

    The ``user_id`` is resolved from the request body, then from the
    authenticated actor, and finally falls back to ``"anonymous"``.

    Raises:
        HTTPException 404: When no agent with *agent_id* is registered.
    """
    from genus.functional_agents.base import AgentContext

    registry = _get_registry(request)
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Resolve user_id: body → actor → fallback
    user_id = body.user_id
    actor = getattr(request.state, "actor", None)
    if not user_id:
        if actor is not None and getattr(actor, "user_id", None):
            user_id = actor.user_id
        else:
            user_id = "anonymous"

    context = AgentContext(
        user_id=user_id,
        session_id=body.session_id,
        actor_id=actor.actor_id if actor else None,
        metadata=body.metadata,
    )

    response = await agent.handle(intent=body.intent, context=context)
    return response.to_dict()


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------


@router.websocket("/v1/agents/{agent_id}/stream")
async def agent_stream(
    websocket: WebSocket,
    agent_id: str,
) -> None:
    """Stream agent responses over WebSocket.

    Auth: ``?token=<api_key>`` query parameter.

    The connection is refused with close-code ``1008`` when the token is
    missing or invalid.  A JSON ``{"type": "error"}`` frame is sent for
    any application-level error (unknown agent, missing intent, etc.).
    """
    from genus.functional_agents.base import AgentContext

    await websocket.accept()

    # Auth via query-parameter (header not available in WebSocket handshake)
    token = websocket.query_params.get("token", "")
    app = websocket.app
    api_keys = getattr(app.state, "api_keys", set())
    if not token or token not in api_keys:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # Resolve agent from registry
    registry = getattr(app.state, "functional_agent_registry", None)
    if registry is None:
        await websocket.send_json(
            {"type": "error", "message": "Functional agent registry not available"}
        )
        await websocket.close()
        return

    agent = registry.get(agent_id)
    if agent is None:
        await websocket.send_json(
            {"type": "error", "message": f"Agent '{agent_id}' not found"}
        )
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "invoke":
                intent = data.get("intent", "").strip()
                if not intent:
                    await websocket.send_json(
                        {"type": "error", "message": "intent must not be empty"}
                    )
                    continue

                user_id = data.get("user_id", "anonymous")
                session_id = data.get("session_id", "default")

                await websocket.send_json({"type": "thinking", "agent_id": agent_id})

                context = AgentContext(
                    user_id=user_id,
                    session_id=session_id,
                )
                response = await agent.handle(intent=intent, context=context)

                await websocket.send_json({
                    "type": "response",
                    "agent_id": response.agent_id,
                    "text": response.text,
                    "success": response.success,
                    "data": response.data,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: agent_id=%s", agent_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("WebSocket error: agent_id=%s error=%s", agent_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            pass
