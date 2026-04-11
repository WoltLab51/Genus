"""
Integration tests for WebSocket chat endpoint — Phase 12+13

Covers:
- Full chat flow: message → thinking → response
- Ping/pong keepalive
- Unauthorized (no token / wrong token) → closed with 1008
- Connection manager not available → error message
- Empty text message → no response (silently skipped)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from genus.api.app import create_app
from genus.api.connection_manager import ConnectionManager
from genus.communication.message_bus import MessageBus

TEST_API_KEY = "chat-ws-test-key"
TEST_SESSION = "test-session"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_llm_router(reply: str = "Hallo! Ich bin GENUS."):
    """Return a mock LLMRouter that always returns *reply*."""
    from genus.llm.models import LLMResponse

    router = MagicMock()
    router.complete = AsyncMock(
        return_value=LLMResponse(
            content=reply,
            model="mock",
            provider="mock",
        )
    )
    return router


def make_client(tmp_path: Path, llm_router=None, with_connection_manager: bool = True):
    """Build a TestClient with a wired ConnectionManager."""
    bus = MessageBus()
    app = create_app(api_key=TEST_API_KEY, message_bus=bus)

    if with_connection_manager:
        app.state.connection_manager = ConnectionManager(
            default_llm_router=llm_router,
            default_bus=bus,
            conversations_dir=tmp_path / "conversations",
        )
    app.state.llm_router = llm_router

    return TestClient(app, raise_server_exceptions=False)


def ws_url(session_id: str = TEST_SESSION, token: str = None) -> str:
    url = f"/ws/chat/{session_id}"
    if token is not None:
        url += f"?token={token}"
    return url


# ---------------------------------------------------------------------------
# Full chat flow
# ---------------------------------------------------------------------------


class TestChatWebSocketFlow:
    def test_full_chat_flow_with_mock_llm(self, tmp_path):
        """Client sends message → receives 'thinking' then 'message' from GENUS."""
        router = make_mock_llm_router("Hey! Mir geht's super.")
        with make_client(tmp_path, llm_router=router) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                ws.send_json({
                    "type": "message",
                    "text": "Hey GENUS, wie geht's?",
                    "user_id": "test-user",
                })
                thinking = ws.receive_json()
                response = ws.receive_json()

        assert thinking["type"] == "thinking"
        assert thinking["sender"] == "GENUS"

        assert response["type"] == "message"
        assert response["sender"] == "GENUS"
        assert response["session_id"] == TEST_SESSION
        assert len(response["text"]) > 0
        assert "timestamp" in response
        assert "intent" in response

    def test_chat_without_llm_fallback_message(self, tmp_path):
        """Without LLM → friendly fallback text, no crash."""
        with make_client(tmp_path, llm_router=None) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                ws.send_json({
                    "type": "message",
                    "text": "Hey GENUS",
                    "user_id": "test",
                })
                ws.receive_json()  # thinking
                response = ws.receive_json()

        assert response["type"] == "message"
        assert len(response["text"]) > 0


# ---------------------------------------------------------------------------
# Ping / Pong
# ---------------------------------------------------------------------------


class TestChatWebSocketPingPong:
    def test_ping_pong(self, tmp_path):
        """Client sends ping → server responds with pong."""
        with make_client(tmp_path) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                ws.send_json({"type": "ping"})
                pong = ws.receive_json()

        assert pong["type"] == "pong"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestChatWebSocketAuth:
    def test_no_token_closes_connection(self, tmp_path):
        """No token → server closes WebSocket with 1008."""
        with make_client(tmp_path) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(ws_url(token=None)) as ws:
                    ws.receive_json()

    def test_wrong_token_closes_connection(self, tmp_path):
        """Wrong token → server closes WebSocket with 1008."""
        with make_client(tmp_path) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(ws_url(token="wrong-token")) as ws:
                    ws.receive_json()


# ---------------------------------------------------------------------------
# No ConnectionManager
# ---------------------------------------------------------------------------


class TestChatWebSocketNoConnectionManager:
    def test_no_connection_manager_sends_error(self, tmp_path):
        """When connection_manager is not in app.state → error message."""
        with make_client(tmp_path, with_connection_manager=False) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "not available" in msg["message"].lower() or "agent" in msg["message"].lower()


# ---------------------------------------------------------------------------
# Empty text
# ---------------------------------------------------------------------------


class TestChatWebSocketEmptyText:
    def test_empty_text_is_skipped_no_response(self, tmp_path):
        """Empty text → no response sent (silently skipped). Ping confirms connection alive."""
        with make_client(tmp_path) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                ws.send_json({"type": "message", "text": "   ", "user_id": "test"})
                ws.send_json({"type": "ping"})
                pong = ws.receive_json()

        assert pong["type"] == "pong"
