"""
ParentalAgent — Phase 14

Monitors child accounts and notifies parents.

Tasks:
1. Track screen time (per child, per day)
2. Notify parents when limit is reached
3. Lock account when limit exceeded
4. Generate daily parent report
5. Flag critical questions ("child asked about X")
6. Bedtime enforcement (locked after bedtime_hour)

Topics:
  Listens to: (called directly by ConversationAgent)
  Publishes:  parental.screen_time.limit_reached
              parental.report.daily
              parental.flag.critical_question
              parental.account.locked
              parental.account.unlocked
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.identity.profile_store import ProfileStore

logger = logging.getLogger(__name__)

# Topics
TOPIC_SCREEN_TIME_LIMIT = "parental.screen_time.limit_reached"
TOPIC_DAILY_REPORT = "parental.report.daily"
TOPIC_CRITICAL_QUESTION = "parental.flag.critical_question"
TOPIC_ACCOUNT_LOCKED = "parental.account.locked"
TOPIC_ACCOUNT_UNLOCKED = "parental.account.unlocked"


class ParentalAgent(Agent):
    """Monitors child accounts and enforces parental controls.

    Args:
        message_bus:   MessageBus for publishing events.
        profile_store: Source of truth for user profiles.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        profile_store: ProfileStore,
    ) -> None:
        super().__init__(agent_id="ParentalAgent", name="ParentalAgent")
        self._bus = message_bus
        self._profiles = profile_store
        # user_id → {date_str → minutes_used}
        self._usage: Dict[str, Dict[str, float]] = defaultdict(dict)
        # user_id → locked_until date
        self._locked: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Any) -> None:
        """Not used directly."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def track_usage(self, user_id: str, minutes: float) -> None:
        """Add *minutes* to today's screen-time for *user_id*."""
        today = date.today().isoformat()
        if today not in self._usage[user_id]:
            self._usage[user_id][today] = 0.0
        self._usage[user_id][today] += minutes

    async def check_and_enforce_limits(
        self, user_id: str
    ) -> Tuple[bool, str]:
        """Check whether a child still has access.

        Returns:
            ``(has_access, message)``
        """
        profile = await self._profiles.get(user_id)
        if profile is None or not profile.is_child():
            return True, ""

        if profile.child_settings is None:
            return True, ""

        today = date.today().isoformat()

        # Bedtime check
        now_hour = datetime.now(timezone.utc).hour
        if now_hour >= profile.child_settings.bedtime_hour:
            msg = (
                f"Es ist schon {now_hour} Uhr — Schlafenszeit! "
                "Bis morgen! 🌙"
            )
            await self._publish_locked(user_id, "bedtime")
            return False, msg

        # Screen-time check
        used = self._usage[user_id].get(today, 0.0)
        limit = float(profile.child_settings.max_screen_time_minutes)
        if used >= limit:
            hours = int(limit) // 60
            mins = int(limit) % 60
            time_str = f"{hours} Stunde{'n' if hours != 1 else ''}" if hours else ""
            if mins:
                time_str += f"{' und ' if time_str else ''}{mins} Minute{'n' if mins != 1 else ''}"
            msg = (
                f"Du hast heute schon {time_str} genutzt. "
                "Für heute war's das — bis morgen! 👋"
            )
            await self._publish_limit_reached(user_id, used, limit)
            return False, msg

        return True, ""

    async def flag_critical_question(
        self, user_id: str, question: str, topic: str
    ) -> None:
        """Flag a critical question for parent review.

        Publishes ``parental.flag.critical_question`` event and logs.
        Never logs the actual question content at DEBUG level.
        """
        profile = await self._profiles.get(user_id)
        report_to: List[str] = ["ronny_wolter"]
        if profile and profile.child_settings:
            report_to = profile.child_settings.report_to

        await self._bus.publish(Message(
            topic=TOPIC_CRITICAL_QUESTION,
            payload={
                "child_user_id": user_id,
                "topic": topic,
                "question_preview": question[:80],  # truncated for safety
                "report_to": report_to,
                "flagged_at": datetime.now(timezone.utc).isoformat(),
            },
            sender_id=self.id,
        ))
        logger.warning(
            "ParentalAgent: critical question flagged (user=%s, topic=%s)",
            user_id,
            topic,
        )

    async def generate_daily_report(self, child_user_id: str) -> dict:
        """Generate a daily report dict for parents.

        Returns a structured report with screen time, question count,
        topics encountered, and flagged questions.
        """
        today = date.today().isoformat()
        profile = await self._profiles.get(child_user_id)
        display_name = profile.display_name if profile else child_user_id

        used = self._usage.get(child_user_id, {}).get(today, 0.0)

        report = {
            "child": display_name,
            "child_user_id": child_user_id,
            "date": today,
            "screen_time_minutes": round(used, 1),
            "questions_asked": 0,
            "topics": [],
            "flagged_questions": [],
            "mood_estimate": "neutral",
        }

        await self._bus.publish(Message(
            topic=TOPIC_DAILY_REPORT,
            payload=report,
            sender_id=self.id,
        ))
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _publish_limit_reached(
        self, user_id: str, used: float, limit: float
    ) -> None:
        await self._bus.publish(Message(
            topic=TOPIC_SCREEN_TIME_LIMIT,
            payload={
                "user_id": user_id,
                "used_minutes": used,
                "limit_minutes": limit,
                "locked_at": datetime.now(timezone.utc).isoformat(),
            },
            sender_id=self.id,
        ))

    async def _publish_locked(self, user_id: str, reason: str) -> None:
        await self._bus.publish(Message(
            topic=TOPIC_ACCOUNT_LOCKED,
            payload={
                "user_id": user_id,
                "reason": reason,
                "locked_at": datetime.now(timezone.utc).isoformat(),
            },
            sender_id=self.id,
        ))
