"""
Orchestrator Process

Standalone process that connects to Redis, runs a single demo orchestration
run, then exits.

Run::

    python -m genus.cli.orchestrator
    python -m genus.cli.orchestrator --problem "add 3 and 4"

Environment variables
---------------------
``GENUS_REDIS_URL``
    Redis connection URL.  Defaults to ``redis://localhost:6379/0``.

The Orchestrator uses the existing
:class:`~genus.orchestration.orchestrator.Orchestrator` class backed by a
:class:`~genus.communication.redis_message_bus.RedisMessageBus`.
"""

import argparse
import asyncio
import logging
import os
import sys

from genus.communication.redis_message_bus import RedisMessageBus
from genus.orchestration.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Orchestrator] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main(problem: str) -> None:
    redis_url = os.environ.get("GENUS_REDIS_URL", "redis://localhost:6379/0")
    logger.info("Connecting to Redis at %s", redis_url)

    bus = RedisMessageBus(redis_url=redis_url)
    await bus.connect()

    orc = Orchestrator(bus)
    await orc.initialize()

    # Give subscriptions time to register with Redis
    await asyncio.sleep(0.2)

    logger.info("Starting run for problem: %r", problem)
    try:
        run_id = await orc.run(problem)
        logger.info("Run completed successfully: run_id=%s", run_id)
    except RuntimeError as exc:
        logger.error("Run failed: %s", exc)
    finally:
        await orc.shutdown()
        await bus.close()


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GENUS Orchestrator – runs a single demo orchestration run via Redis."
    )
    parser.add_argument(
        "--problem",
        default="demo problem: echo and summarize",
        help="Problem/goal description for the run (default: demo).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(main(args.problem))
    except KeyboardInterrupt:
        sys.exit(0)
