"""
CLI producer for ``outcome.recorded`` events.

Usage::

    python -m genus.cli.outcome \\
        --run-id   <run_id>     \\
        --outcome  good|bad|unknown \\
        --score-delta  <float>  \\
        [--notes   "<text>"]    \\
        [--source  user]        \\
        [--timestamp 2026-04-05T17:00:00+00:00]

``--run-id`` is **required**.  If ``--timestamp`` is omitted the current
UTC time is used automatically.

The message is published on the existing :class:`~genus.communication.message_bus.MessageBus`
with:
    topic     = ``outcome.recorded``
    sender_id = ``OutcomeCLI``
    payload   = validated outcome payload dict
    metadata  = ``{"run_id": <run_id>}``

Persistence is handled by :class:`~genus.agents.event_recorder_agent.EventRecorderAgent`
(already subscribes to ``outcome.recorded`` by default).  This CLI must
not write files directly.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from genus.communication.message_bus import Message, MessageBus
from genus.feedback.outcome import validate_outcome_payload

SENDER_ID = "OutcomeCLI"
TOPIC = "outcome.recorded"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m genus.cli.outcome",
        description="Publish an outcome.recorded event onto the GENUS MessageBus.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier (stored in message metadata).",
    )
    parser.add_argument(
        "--outcome",
        required=True,
        choices=["good", "bad", "unknown"],
        help="Outcome value.",
    )
    parser.add_argument(
        "--score-delta",
        required=True,
        type=float,
        dest="score_delta",
        help="Score delta float; clamped to [-10.0, 10.0].",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional annotation (max 256 chars).",
    )
    parser.add_argument(
        "--source",
        default="user",
        help="Source of the outcome (max 64 chars, default: 'user').",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="ISO-8601 timestamp; defaults to current UTC if omitted.",
    )
    return parser


def build_message(args: argparse.Namespace, bus: MessageBus) -> Message:
    """Validate *args* and return a ready-to-publish :class:`Message`.

    Args:
        args: Parsed argument namespace from :func:`_build_parser`.
        bus:  MessageBus (not used here; passed for future extension hooks).

    Returns:
        A :class:`~genus.communication.message_bus.Message` ready to publish.

    Raises:
        ValueError: If payload validation fails.
        SystemExit: Never raised here; the caller handles argparse errors.
    """
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()

    raw_payload = {
        "outcome": args.outcome,
        "score_delta": args.score_delta,
        "source": args.source,
        "timestamp": timestamp,
    }
    if args.notes is not None:
        raw_payload["notes"] = args.notes

    validated = validate_outcome_payload(raw_payload)
    payload_dict = validated.to_message_payload()

    return Message(
        topic=TOPIC,
        payload=payload_dict,
        sender_id=SENDER_ID,
        metadata={"run_id": args.run_id},
    )


async def _async_main(argv=None, bus: MessageBus = None) -> None:
    """Async entry-point – separated so tests can inject a custom *bus*.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).
        bus:  Optional :class:`MessageBus` instance; a fresh one is created
              when not provided (useful in tests).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if bus is None:
        bus = MessageBus()

    message = build_message(args, bus)
    await bus.publish(message)


def main(argv=None, bus: MessageBus = None) -> None:
    """Synchronous entry-point invoked by ``python -m genus.cli.outcome``."""
    asyncio.run(_async_main(argv=argv, bus=bus))


if __name__ == "__main__":
    main()
