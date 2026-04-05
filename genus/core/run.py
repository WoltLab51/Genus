"""
Run Management Module

Provides utilities for creating and managing GENUS run identifiers.
A run_id is a human-readable, unique identifier that encodes:
  - UTC timestamp (ISO-ish, filesystem-safe)
  - normalized slug derived from the task/goal name
  - short random suffix for collision avoidance

run_id is carried in Message.metadata["run_id"] and is required by
all core agents.
"""

import re
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from genus.communication.message_bus import Message


_SLUG_MAX_LEN = 32
_SUFFIX_LEN = 6
_SUFFIX_CHARS = string.ascii_lowercase + string.digits


def _normalize_slug(raw: str) -> str:
    """Return a URL/filename-safe lowercase slug from *raw*.

    Converts to lowercase, replaces runs of non-alphanumeric characters
    with a single hyphen, strips leading/trailing hyphens, and truncates
    to *_SLUG_MAX_LEN* characters.
    """
    slug = raw.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:_SLUG_MAX_LEN] if slug else "run"


def _random_suffix(length: int = _SUFFIX_LEN, rng: Optional[random.Random] = None) -> str:
    """Return a short alphanumeric random suffix."""
    src = rng or random
    return "".join(src.choices(_SUFFIX_CHARS, k=length))


def new_run_id(
    slug: Optional[str] = None,
    now: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """Generate a new, human-readable, unique run ID.

    Format::

        2026-04-05T14-07-12Z__task-review__k3m9f2

    Args:
        slug: Optional label for the run (e.g. task type or goal name).
              Normalised automatically.  Defaults to ``"run"``.
        now:  UTC datetime to use as the timestamp.  Injected for tests;
              defaults to the current UTC time.
        rng:  Optional :class:`random.Random` instance for reproducible
              tests.

    Returns:
        A unique, human-readable run ID string.
    """
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_slug = _normalize_slug(slug) if slug else "run"
    suffix = _random_suffix(rng=rng)
    return f"{ts}__{safe_slug}__{suffix}"


@dataclass
class RunContext:
    """Lightweight context object for a single GENUS run.

    Attributes:
        run_id:        The unique run identifier (see :func:`new_run_id`).
        created_at:    UTC datetime when the run was created.
        labels:        Arbitrary key-value metadata for the run (e.g. risk,
                       task_type).
        parent_run_id: Optional ID of the parent run for nested runs (P1+).
    """

    run_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, Any] = field(default_factory=dict)
    parent_run_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        slug: Optional[str] = None,
        labels: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
        rng: Optional[random.Random] = None,
    ) -> "RunContext":
        """Create a new :class:`RunContext` with a freshly generated run_id."""
        ts = now or datetime.now(timezone.utc)
        run_id = new_run_id(slug=slug, now=ts, rng=rng)
        return cls(run_id=run_id, created_at=ts, labels=labels or {})


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def attach_run_id(message: Message, run_id: str) -> Message:
    """Return a copy of *message* with ``metadata["run_id"]`` set to *run_id*.

    The original message is **not** mutated.
    """
    new_metadata = dict(message.metadata)
    new_metadata["run_id"] = run_id
    return Message(
        topic=message.topic,
        payload=message.payload,
        sender_id=message.sender_id,
        message_id=message.message_id,
        timestamp=message.timestamp,
        priority=message.priority,
        metadata=new_metadata,
    )


def get_run_id(message: Message) -> Optional[str]:
    """Return the run_id from ``message.metadata``, or ``None`` if absent."""
    return message.metadata.get("run_id")


def require_run_id(message: Message) -> str:
    """Return the run_id from ``message.metadata``.

    Raises:
        ValueError: If ``run_id`` is not present in ``message.metadata``.
    """
    run_id = message.metadata.get("run_id")
    if run_id is None:
        raise ValueError(f"Message {message.message_id!r} is missing required metadata 'run_id'")
    return run_id
