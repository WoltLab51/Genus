"""
WebSocket Chat Endpoint — Phase 12

Provides ``/ws/chat/{session_id}`` for real-time conversation with GENUS.

Protocol (JSON):

Client → Server:
    {"type": "message", "text": "...", "user_id": "...", "metadata": {}}
    {"type": "ping"}

Server → Client:
    {"type": "thinking", "sender": "GENUS"}
    {"type": "message",  "text": "...", "sender": "GENUS",
     "session_id": "...", "timestamp": "...", "intent": "...", "run_id": null}
    {"type": "pong"}
    {"type": "error",   "message": "...", "code": "..."}

Auth: query-parameter ``?token=<api_key>``.
Missing / wrong token → WebSocket closed with code 1008.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from genus.api.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """WebSocket endpoint for real-time chat with GENUS."""
    await websocket.accept()

    # Auth via query-parameter
    token = websocket.query_params.get("token", "")
    app = websocket.app
    api_keys = getattr(app.state, "api_keys", set())
    if not token or token not in api_keys:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    # Retrieve ConversationAgent for this session
    connection_manager: ConnectionManager = getattr(
        app.state, "connection_manager", None
    )
    if connection_manager is None:
        await websocket.send_json(
            {"type": "error", "message": "ConversationAgent not available", "code": "no_agent"}
        )
        await websocket.close()
        return

    bus = getattr(app.state, "message_bus", None)
    llm_router = getattr(app.state, "llm_router", None)
    session = connection_manager.get_or_create_session(session_id, llm_router, bus)
    conversation_agent = session.agent

    try:
        while True:
            data = await websocket.receive_json()

            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "message":
                text = data.get("text", "").strip()
                user_id = data.get("user_id", "anonymous")

                if not text:
                    continue

                # Acknowledge that GENUS is thinking
                await websocket.send_json({"type": "thinking", "sender": "GENUS"})

                response = await conversation_agent.process_user_message(
                    text=text,
                    user_id=user_id,
                    session_id=session_id,
                )

                session.touch()

                await websocket.send_json({
                    "type": "message",
                    "text": response.text,
                    "sender": "GENUS",
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "intent": response.intent,
                    "run_id": response.run_id,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("WebSocket error: session=%s error=%s", session_id, exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            pass
