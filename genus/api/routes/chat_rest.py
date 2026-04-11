"""
REST Chat Endpoint — Phase 12 (fallback for clients that can't use WebSocket)

POST /chat

Request body:
    {"text": "Hey GENUS", "user_id": "...", "session_id": "..."}

Response:
    {"text": "...", "sender": "GENUS", "session_id": "...",
     "intent": "...", "timestamp": "...", "run_id": null}

Auth: standard Bearer API key (enforced by ApiKeyMiddleware).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from genus.api.connection_manager import ConnectionManager
from genus.api.deps import verify_reader

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    text: str
    user_id: str = "anonymous"
    session_id: Optional[str] = None


@router.post("/chat")
async def chat_rest(
    body: ChatRequest,
    request: Request,
    _: None = Depends(verify_reader),
) -> JSONResponse:
    """REST fallback for real-time chat with GENUS."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")

    import uuid
    session_id = body.session_id or str(uuid.uuid4())

    connection_manager: ConnectionManager = getattr(
        request.app.state, "connection_manager", None
    )
    if connection_manager is None:
        raise HTTPException(status_code=503, detail="ConversationAgent not available")

    llm_router = getattr(request.app.state, "llm_router", None)
    bus = getattr(request.app.state, "message_bus", None)
    session = connection_manager.get_or_create_session(session_id, llm_router, bus)
    conversation_agent = session.agent

    response = await conversation_agent.process_user_message(
        text=text,
        user_id=body.user_id,
        session_id=session_id,
    )
    session.touch()

    return JSONResponse({
        "text": response.text,
        "sender": "GENUS",
        "session_id": session_id,
        "intent": response.intent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": response.run_id,
    })
