"""
Message Serialization

Pure functions for converting :class:`~genus.communication.message_bus.Message`
objects to and from JSON-safe dicts, suitable for transport over Redis Pub/Sub
or any other serialization boundary.

Design rules:
- :func:`message_to_dict` produces a JSON-safe ``dict`` (no datetime objects,
  priority stored as its name string).
- :func:`message_from_dict` reconstructs a ``Message`` from that dict.
- ``run_id`` and all other metadata keys are preserved.
- ``payload`` and ``metadata`` values must already be JSON-compatible before
  calling :func:`message_to_dict` (dicts, lists, str, int, float, bool, None).
- No IO, no MessageBus dependency.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from genus.communication.message_bus import Message, MessagePriority


def message_to_dict(message: Message) -> Dict[str, Any]:
    """Serialize *message* to a JSON-safe ``dict``.

    Args:
        message: The :class:`~genus.communication.message_bus.Message` to
                 serialize.

    Returns:
        A ``dict`` with the following keys:

        - ``message_id``  – UUID string
        - ``topic``       – topic string
        - ``sender_id``   – sender identifier string
        - ``timestamp``   – ISO 8601 string in UTC (e.g. ``"2026-04-05T19:40:20.380000Z"``)
        - ``priority``    – priority name string (e.g. ``"NORMAL"``)
        - ``payload``     – payload value (must already be JSON-compatible)
        - ``metadata``    – metadata dict (must already be JSON-compatible)
    """
    ts = message.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "message_id": message.message_id,
        "topic": message.topic,
        "sender_id": message.sender_id,
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "priority": message.priority.name,
        "payload": message.payload,
        "metadata": dict(message.metadata),
    }


def message_from_dict(d: Dict[str, Any]) -> Message:
    """Deserialize a ``dict`` produced by :func:`message_to_dict` back to a
    :class:`~genus.communication.message_bus.Message`.

    Args:
        d: The dict to deserialize.  Must contain all keys produced by
           :func:`message_to_dict`.

    Returns:
        A :class:`~genus.communication.message_bus.Message` instance.

    Raises:
        KeyError:  If a required key is missing.
        ValueError: If the priority name or timestamp string is invalid.
    """
    ts_str: str = d["timestamp"]
    # Parse ISO 8601 UTC timestamp
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    try:
        timestamp = datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError):
        # Fallback: strip timezone suffix and parse as UTC
        ts_plain = d["timestamp"].rstrip("Z").split("+")[0]
        timestamp = datetime.strptime(ts_plain, "%Y-%m-%dT%H:%M:%S.%f").replace(
            tzinfo=timezone.utc
        )

    priority = MessagePriority[d["priority"]]

    return Message(
        message_id=d["message_id"],
        topic=d["topic"],
        sender_id=d["sender_id"],
        timestamp=timestamp,
        priority=priority,
        payload=d["payload"],
        metadata=dict(d["metadata"]),
    )
