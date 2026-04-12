"""
NightScheduler — Phase 14b

Runs a nightly compression job at 02:00 UTC.

Each night it:
1. Scans ``var/conversations/*.jsonl`` for uncompressed sessions.
2. Publishes ``memory.compress.requested`` for each new session.
3. Records compressed sessions in ``var/compressed_sessions.jsonl`` to avoid
   reprocessing.

No external dependencies — uses only ``asyncio.sleep``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from genus.communication.message_bus import Message, MessageBus

logger = logging.getLogger(__name__)

_DEFAULT_CONVERSATIONS_DIR = "var/conversations"
_DEFAULT_COMPRESSED_LOG = "var/compressed_sessions.jsonl"
_TOPIC_COMPRESS_REQUESTED = "memory.compress.requested"


class NightScheduler:
    """Schedules nightly compression of conversation sessions.

    Args:
        message_bus:        The shared :class:`~genus.communication.message_bus.MessageBus`.
        conversations_dir:  Directory that contains ``<session_id>.jsonl`` files.
                            Defaults to ``var/conversations``.
        compressed_log:     Path to the append-only JSONL file that tracks which
                            sessions have already been compressed.
                            Defaults to ``var/compressed_sessions.jsonl``.
        run_hour_utc:       Hour (0–23 UTC) at which to run the job.
                            Defaults to 2 (02:00 UTC).
    """

    def __init__(
        self,
        message_bus: MessageBus,
        *,
        conversations_dir: str = _DEFAULT_CONVERSATIONS_DIR,
        compressed_log: str = _DEFAULT_COMPRESSED_LOG,
        run_hour_utc: int = 2,
    ) -> None:
        self._bus = message_bus
        self._conversations_dir = Path(conversations_dir)
        self._compressed_log = Path(compressed_log)
        self._run_hour_utc = run_hour_utc
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background asyncio task."""
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._loop())
            logger.info("NightScheduler started (runs at %02d:00 UTC)", self._run_hour_utc)

    def stop(self) -> None:
        """Cancel the background asyncio task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            logger.info("NightScheduler stopped")
        self._task = None

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Main scheduler loop — waits until run_hour_utc, then compresses."""
        while True:
            await self._wait_until_run_hour()
            await self._run_nightly_compression()
            # Sleep 60 s after running so we don't trigger twice within the same minute
            await asyncio.sleep(60)

    async def _wait_until_run_hour(self) -> None:
        """Sleep until the next occurrence of ``run_hour_utc``."""
        now = datetime.now(timezone.utc)
        target_hour = self._run_hour_utc
        seconds_until = (target_hour - now.hour) % 24 * 3600 - now.minute * 60 - now.second
        if seconds_until <= 0:
            seconds_until += 24 * 3600
        await asyncio.sleep(seconds_until)

    async def _run_nightly_compression(self) -> None:
        """Scan conversations dir and publish compress.requested for new sessions."""
        if not self._conversations_dir.exists():
            logger.debug(
                "NightScheduler: conversations dir %s does not exist — skipping",
                self._conversations_dir,
            )
            return

        already_compressed = self._load_compressed_sessions()
        count = 0

        for path in sorted(self._conversations_dir.glob("*.jsonl")):
            session_id = path.stem  # filename without .jsonl

            if session_id in already_compressed:
                logger.debug("NightScheduler: skipping already-compressed session %s", session_id)
                continue

            # Read messages from the JSONL file
            messages = self._load_messages(path)
            if not messages:
                logger.debug("NightScheduler: skipping empty session %s", session_id)
                continue

            # Infer user_id from the first message, fall back to "unknown"
            user_id = self._infer_user_id(messages, session_id)

            await self._bus.publish(Message(
                topic=_TOPIC_COMPRESS_REQUESTED,
                payload={
                    "session_id": session_id,
                    "user_id": user_id,
                    "messages": messages,
                },
                sender_id="NightScheduler",
            ))

            self._mark_compressed(session_id)
            count += 1

        logger.info("NightScheduler: published compress.requested for %d session(s)", count)

    # ------------------------------------------------------------------
    # Compressed-sessions log
    # ------------------------------------------------------------------

    def _mark_compressed(self, session_id: str) -> None:
        """Append *session_id* to the compressed-sessions log."""
        self._compressed_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self._compressed_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"session_id": session_id}) + "\n")

    def _load_compressed_sessions(self) -> Set[str]:
        """Return the set of already-compressed session IDs."""
        if not self._compressed_log.exists():
            return set()

        ids: Set[str] = set()
        try:
            with open(self._compressed_log, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sid = record.get("session_id")
                        if sid:
                            ids.add(sid)
                    except json.JSONDecodeError as exc:
                        logger.warning("NightScheduler: bad line in compressed log: %s", exc)
        except OSError as exc:
            logger.warning("NightScheduler: could not read compressed log: %s", exc)

        return ids

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_messages(path: Path) -> list:
        """Load messages from a conversation JSONL file."""
        messages = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return messages

    @staticmethod
    def _infer_user_id(messages: list, fallback: str) -> str:
        """Try to infer the user_id from a message payload, or use *fallback*."""
        for m in messages:
            uid = m.get("user_id") or m.get("userId")
            if uid:
                return str(uid)
        return fallback
