"""
Unit tests for GET /runs/{run_id}/ws — WebSocket live-status streaming

Covers:
- Unauthorized connection (no token) → error + close
- Unauthorized connection (wrong token) → error + close
- Non-existent run → error + close
- Successful connect → {"type": "connected", "run_id": ...}
- Bus event forwarded to WebSocket
- Connection closes automatically after terminal event
- Events for a different run_id are not forwarded
"""

import asyncio
import tempfile

import pytest
from fastapi.testclient import TestClient

from genus.api.app import create_app
from genus.communication.message_bus import Message, MessageBus
from genus.dev.topics import DEV_LOOP_COMPLETED, DEV_LOOP_FAILED, DEV_LOOP_STARTED
from genus.memory.run_journal import RunJournal
from genus.memory.store_jsonl import JsonlRunStore

TEST_API_KEY = "ws-test-key"
TEST_RUN_ID = "ws-run-001"
OTHER_RUN_ID = "ws-run-999"
TEST_GOAL = "stream events live"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_store(tmp_path):
    """Return a JsonlRunStore backed by tmp_path."""
    return JsonlRunStore(base_dir=str(tmp_path))


def make_run(store, run_id=TEST_RUN_ID, goal=TEST_GOAL):
    """Initialize a run in *store* and return the store."""
    journal = RunJournal(run_id, store)
    journal.initialize(goal=goal)
    return store


def make_client(store, bus=None):
    """Return a TestClient with the given store and optional bus."""
    app = create_app(api_key=TEST_API_KEY, run_store=store, message_bus=bus)
    return TestClient(app, raise_server_exceptions=False)


def ws_url(run_id=TEST_RUN_ID, token=None):
    url = f"/runs/{run_id}/ws"
    if token is not None:
        url += f"?token={token}"
    return url


def _publish_sync(bus: MessageBus, msg: Message) -> None:
    """Run bus.publish(msg) in a fresh event loop (test helper)."""
    asyncio.run(bus.publish(msg))


def _make_msg(topic: str, run_id: str, payload=None) -> Message:
    return Message(
        topic=topic,
        payload=payload or {},
        sender_id="test",
        metadata={"run_id": run_id},
    )


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestWsUnauthorized:
    def test_ws_no_token_sends_error(self, tmp_path):
        store = make_run(make_store(tmp_path))
        with make_client(store) as client:
            with client.websocket_connect(ws_url(token=None)) as ws:
                data = ws.receive_json()
        assert data["type"] == "error"
        assert "unauthorized" in data["message"].lower()

    def test_ws_wrong_token_sends_error(self, tmp_path):
        store = make_run(make_store(tmp_path))
        with make_client(store) as client:
            with client.websocket_connect(ws_url(token="wrong-key")) as ws:
                data = ws.receive_json()
        assert data["type"] == "error"
        assert "unauthorized" in data["message"].lower()


# ---------------------------------------------------------------------------
# Run-not-found
# ---------------------------------------------------------------------------


class TestWsRunNotFound:
    def test_ws_run_not_found_sends_error(self, tmp_path):
        store = make_store(tmp_path)  # no run initialized
        with make_client(store) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                data = ws.receive_json()
        assert data["type"] == "error"
        assert "not found" in data["message"].lower()


# ---------------------------------------------------------------------------
# Connected message
# ---------------------------------------------------------------------------


class TestWsConnected:
    def test_ws_connected_message_received(self, tmp_path):
        store = make_run(make_store(tmp_path))
        bus = MessageBus()
        with make_client(store, bus=bus) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                data = ws.receive_json()
        assert data["type"] == "connected"
        assert data["run_id"] == TEST_RUN_ID


# ---------------------------------------------------------------------------
# Event forwarding
# ---------------------------------------------------------------------------


class TestWsEventForwarding:
    def test_ws_receives_event_on_bus_publish(self, tmp_path):
        """Bus publish for the correct run_id is forwarded to the WebSocket client."""
        store = make_run(make_store(tmp_path))
        bus = MessageBus()
        with make_client(store, bus=bus) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                # Consume the initial "connected" message
                connected = ws.receive_json()
                assert connected["type"] == "connected"

                # Publish a non-terminal event from "outside" (different event loop)
                msg = _make_msg(DEV_LOOP_STARTED, TEST_RUN_ID, {"info": "started"})
                _publish_sync(bus, msg)

                event = ws.receive_json()

        assert event["type"] == "event"
        assert event["topic"] == DEV_LOOP_STARTED
        assert event["run_id"] == TEST_RUN_ID
        assert event["payload"] == {"info": "started"}

    def test_ws_closes_after_terminal_event(self, tmp_path):
        """After dev.loop.completed the handler closes the connection."""
        store = make_run(make_store(tmp_path))
        bus = MessageBus()
        with make_client(store, bus=bus) as client:
            with client.websocket_connect(ws_url(token=TEST_API_KEY)) as ws:
                # Consume "connected"
                ws.receive_json()

                # Publish terminal event
                msg = _make_msg(DEV_LOOP_COMPLETED, TEST_RUN_ID)
                _publish_sync(bus, msg)

                # Should receive the event
                event = ws.receive_json()

        assert event["type"] == "event"
        assert event["topic"] == DEV_LOOP_COMPLETED

    def test_ws_wrong_run_id_filtered(self, tmp_path):
        """Events for a different run_id must NOT be forwarded."""
        store = make_store(tmp_path)
        # Initialize both runs
        make_run(store, run_id=TEST_RUN_ID)
        make_run(store, run_id=OTHER_RUN_ID)

        bus = MessageBus()
        with make_client(store, bus=bus) as client:
            with client.websocket_connect(ws_url(run_id=TEST_RUN_ID, token=TEST_API_KEY)) as ws:
                ws.receive_json()  # "connected"

                # Publish event for the OTHER run — should be filtered
                other_msg = _make_msg(DEV_LOOP_STARTED, OTHER_RUN_ID)
                _publish_sync(bus, other_msg)

                # Publish terminal event for the CORRECT run so the handler exits
                own_msg = _make_msg(DEV_LOOP_COMPLETED, TEST_RUN_ID)
                _publish_sync(bus, own_msg)

                # We should only receive the event for the correct run
                event = ws.receive_json()

        assert event["type"] == "event"
        assert event["run_id"] == TEST_RUN_ID
        assert event["topic"] == DEV_LOOP_COMPLETED
