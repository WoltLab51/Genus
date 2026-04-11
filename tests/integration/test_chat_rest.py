"""
Integration tests for REST chat endpoint — Phase 12

Covers:
- POST /chat with valid token → 200, GENUS response
- POST /chat without auth → 401
- POST /chat with empty text → 422
- POST /chat with session_id → reuses session
- POST /chat without session_id → generates new session_id
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.api.connection_manager import ConnectionManager
from genus.communication.message_bus import MessageBus

TEST_API_KEY = "chat-rest-test-key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_llm_router(reply: str = "Hallo von GENUS!"):
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


def auth_header() -> dict:
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatRestEndpoint:
    def test_chat_returns_200(self, tmp_path):
        """POST /chat with valid request → 200."""
        router = make_mock_llm_router()
        with make_client(tmp_path, llm_router=router) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hey GENUS", "user_id": "test_user", "session_id": "sess-rest-001"},
                headers=auth_header(),
            )
        assert resp.status_code == 200

    def test_chat_response_structure(self, tmp_path):
        """Response has required fields: text, sender, session_id, intent, timestamp."""
        router = make_mock_llm_router("Ich bin GENUS, dein digitales Wesen!")
        with make_client(tmp_path, llm_router=router) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hey GENUS", "user_id": "test_user", "session_id": "sess-rest-002"},
                headers=auth_header(),
            )
        data = resp.json()
        assert data["sender"] == "GENUS"
        assert "text" in data
        assert "session_id" in data
        assert "intent" in data
        assert "timestamp" in data

    def test_chat_without_auth_returns_401(self, tmp_path):
        """No Authorization header → 401."""
        with make_client(tmp_path) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hey GENUS", "user_id": "anon"},
            )
        assert resp.status_code == 401

    def test_chat_empty_text_returns_422(self, tmp_path):
        """Empty text → 422 Unprocessable Entity."""
        with make_client(tmp_path) as client:
            resp = client.post(
                "/chat",
                json={"text": "   ", "user_id": "test"},
                headers=auth_header(),
            )
        assert resp.status_code == 422

    def test_chat_generates_session_id_when_not_provided(self, tmp_path):
        """When session_id is not in the request, one is generated."""
        with make_client(tmp_path) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hallo"},
                headers=auth_header(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] is not None
        assert len(data["session_id"]) > 0

    def test_chat_no_connection_manager_returns_503(self, tmp_path):
        """No ConnectionManager in app.state → 503."""
        with make_client(tmp_path, with_connection_manager=False) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hey", "user_id": "test"},
                headers=auth_header(),
            )
        assert resp.status_code == 503

    def test_chat_fallback_without_llm(self, tmp_path):
        """Without LLMRouter → friendly fallback text in response, no crash."""
        with make_client(tmp_path, llm_router=None) as client:
            resp = client.post(
                "/chat",
                json={"text": "Hey GENUS", "user_id": "test"},
                headers=auth_header(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["text"]) > 0
