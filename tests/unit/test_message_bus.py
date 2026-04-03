"""Unit tests for the unified MessageBus."""

import pytest
from genus.communication.message_bus import MessageBus, Message


class TestMessageCreation:

    def test_defaults(self):
        m = Message(topic="t", payload={"a": 1})
        assert m.topic == "t"
        assert m.payload == {"a": 1}
        assert m.message_id
        assert m.timestamp

    def test_to_dict(self):
        m = Message(topic="t", payload={}, sender="x")
        d = m.to_dict()
        assert d["topic"] == "t"
        assert d["sender"] == "x"


class TestSubscribePublish:

    @pytest.mark.asyncio
    async def test_basic(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("t", handler)
        await bus.publish_event("t", {"v": 1})
        assert len(received) == 1
        assert received[0].payload["v"] == 1

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = MessageBus()
        r1, r2 = [], []

        async def h1(m):
            r1.append(m)

        async def h2(m):
            r2.append(m)

        bus.subscribe("t", h1)
        bus.subscribe("t", h2)
        await bus.publish_event("t", {})
        assert len(r1) == 1 and len(r2) == 1

    @pytest.mark.asyncio
    async def test_topic_isolation(self):
        bus = MessageBus()
        r1, r2 = [], []

        async def h1(m):
            r1.append(m)

        async def h2(m):
            r2.append(m)

        bus.subscribe("a", h1)
        bus.subscribe("b", h2)
        await bus.publish_event("a", {"x": 1})
        assert len(r1) == 1 and len(r2) == 0


class TestUnsubscribe:

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("t", handler)
        await bus.publish_event("t", {})
        assert len(received) == 1

        bus.unsubscribe("t", handler)
        await bus.publish_event("t", {})
        assert len(received) == 1  # not incremented

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self):
        bus = MessageBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("t", handler)
        bus.unsubscribe_all("t")
        await bus.publish_event("t", {})
        assert len(received) == 0


class TestHistory:

    @pytest.mark.asyncio
    async def test_history_recorded(self):
        bus = MessageBus()
        await bus.publish_event("h", {"d": 1})
        h = bus.get_history()
        assert len(h) == 1 and h[0].topic == "h"

    @pytest.mark.asyncio
    async def test_history_limit(self):
        bus = MessageBus(max_history=5)
        for i in range(10):
            await bus.publish_event("h", {"i": i})
        assert len(bus.get_history(limit=100)) == 5

    @pytest.mark.asyncio
    async def test_history_filter_by_topic(self):
        bus = MessageBus()
        await bus.publish_event("a", {})
        await bus.publish_event("b", {})
        assert len(bus.get_history(topic="a")) == 1

    def test_clear_history(self):
        bus = MessageBus()
        bus._history.append(Message(topic="x", payload={}))
        bus.clear_history()
        assert len(bus.get_history()) == 0


class TestTopics:

    def test_get_topics(self):
        bus = MessageBus()

        async def noop(m):
            pass

        bus.subscribe("a", noop)
        bus.subscribe("b", noop)
        assert set(bus.get_topics()) == {"a", "b"}

    def test_subscriber_count(self):
        bus = MessageBus()

        async def noop(m):
            pass

        assert bus.get_subscriber_count("x") == 0
        bus.subscribe("x", noop)
        assert bus.get_subscriber_count("x") == 1
