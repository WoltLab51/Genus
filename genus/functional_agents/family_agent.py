"""Family Agent — GENUS-2.0

Functional agent for family management: members, tasks, appointments,
reminders, and household coordination.

The current implementation provides the intent-handling wiring and
response structure. Integration with calendar backends, task stores, or
notification channels is done via the GENUS tool layer.
"""

from __future__ import annotations

import logging
from typing import List

from genus.functional_agents.base import AgentContext, AgentResponse, FunctionalAgent

logger = logging.getLogger(__name__)

# Keywords that indicate a family-management intent (German + English).
_FAMILY_KEYWORDS: List[str] = [
    "familie", "family",
    "aufgabe", "task", "todo", "to-do",
    "termin", "appointment", "kalender", "calendar",
    "kind", "child", "mama", "papa", "eltern", "parent",
    "mitglied", "member",
    "erinnerung", "reminder",
    "haushalt", "household",
    "einkauf", "shopping", "einkaufsliste",
    "schule", "school", "hausaufgaben", "homework",
    "urlaub", "vacation", "ferien",
]


class FamilyAgent(FunctionalAgent):
    """Family management functional agent.

    Handles intents related to family members, tasks, appointments, and
    household coordination.

    Example::

        agent = FamilyAgent()
        ctx = AgentContext(user_id="mama", session_id="s1")
        response = await agent.handle("Termin morgen 14 Uhr beim Arzt", ctx)
        print(response.text)
    """

    agent_id = "family"
    role = "family_management"
    description = "Familien-Management: Mitglieder, Aufgaben, Termine"
    allowed_tools: List[str] = [
        "calendar",
        "task_store",
        "notification",
        "reminder",
    ]
    required_scope = "system"

    async def handle(self, intent: str, context: AgentContext) -> AgentResponse:
        """Handle a family-management intent.

        Args:
            intent:  User intent string (e.g. ``"Termin morgen 14 Uhr beim Arzt"``).
            context: Request context.

        Returns:
            :class:`AgentResponse` describing the planned or executed action.
        """
        logger.info(
            "FamilyAgent.handle: user_id=%s intent=%r",
            context.user_id,
            intent,
        )
        return AgentResponse(
            agent_id=self.agent_id,
            text=(
                f"Familien-Anfrage empfangen: \"{intent}\". "
                "Familien-Verwaltung wird ausgeführt."
            ),
            data={
                "intent": intent,
                "user_id": context.user_id,
                "session_id": context.session_id,
            },
        )

    async def can_handle(self, intent: str) -> bool:
        """Return True when *intent* contains family-related keywords.

        Args:
            intent: Natural-language intent string.

        Returns:
            True if the agent should handle this intent.
        """
        intent_lower = intent.lower()
        return any(kw in intent_lower for kw in _FAMILY_KEYWORDS)
