"""Unit tests for EventBus."""
import pytest
from genus.communication import EventBus, Event


async def test_event_creation():
    """Test creating events."""
    event = Event(event_type="test.event", data={"key": "value"}, source="test")

    assert event.event_type == "test.event"
    assert event.data["key"] == "value"
    assert event.source == "test"
    assert event.timestamp is not None


async def test_event_bus_creation():
    """Test creating an event bus."""
    bus = EventBus()
    assert bus is not None
    assert bus.get_events() == []


async def test_event_bus_emit():
    """Test emitting events."""
    bus = EventBus()
    received = []

    async def listener(event):
        received.append(event)

    bus.subscribe("test.event", listener)

    event = Event(event_type="test.event", data={"info": "test"})
    await bus.emit(event)

    assert len(received) == 1
    assert received[0].data["info"] == "test"


async def test_event_bus_emit_event():
    """Test convenience method for emitting events."""
    bus = EventBus()
    received = []

    async def listener(event):
        received.append(event)

    bus.subscribe("test.event", listener)

    await bus.emit_event("test.event", {"info": "test"}, source="test-source")

    assert len(received) == 1
    assert received[0].data["info"] == "test"
    assert received[0].source == "test-source"


async def test_event_bus_get_events():
    """Test retrieving events."""
    bus = EventBus()

    await bus.emit_event("event1", {"data": "1"})
    await bus.emit_event("event2", {"data": "2"})
    await bus.emit_event("event1", {"data": "3"})

    all_events = bus.get_events()
    assert len(all_events) == 3

    event1_only = bus.get_events(event_type="event1")
    assert len(event1_only) == 2


async def test_event_bus_clear_log():
    """Test clearing event log."""
    bus = EventBus()

    await bus.emit_event("event1", {"data": "1"})
    await bus.emit_event("event2", {"data": "2"})

    assert len(bus.get_events()) == 2

    bus.clear_log()

    assert len(bus.get_events()) == 0


async def test_event_to_dict():
    """Test converting event to dictionary."""
    event = Event(event_type="test.event", data={"key": "value"}, source="test")
    event_dict = event.to_dict()

    assert event_dict["event_type"] == "test.event"
    assert event_dict["data"]["key"] == "value"
    assert event_dict["source"] == "test"
    assert "timestamp" in event_dict
