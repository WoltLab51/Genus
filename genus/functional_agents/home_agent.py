"""Home Agent — GENUS-2.0

Functional agent for smart-home control: lights, heating, cameras,
switches, blinds, speakers, routines, and automations.

A full production implementation would dispatch commands to Home Assistant,
MQTT, or another home-automation backend via the GENUS tool layer.
The current implementation provides the wiring and response structure;
the integration details are left to the deployment configuration.
"""

from __future__ import annotations

import logging
from typing import List

from genus.functional_agents.base import AgentContext, AgentResponse, FunctionalAgent

logger = logging.getLogger(__name__)

# Keywords that indicate a home-control intent (German + English).
_HOME_KEYWORDS: List[str] = [
    "licht", "light", "lamp", "lampe",
    "heizung", "heating", "thermostat",
    "kamera", "camera", "alarm",
    "steckdose", "outlet", "schalter", "switch",
    "rollo", "rolladen", "blind",
    "musik", "music", "lautsprecher", "speaker",
    "smart home", "smarthome", "gerät", "device",
    "routine", "automation",
    "temperatur", "temperature",
    "fenster", "window", "tür", "door",
]


class HomeAgent(FunctionalAgent):
    """Smart-Home functional agent.

    Handles intents related to home devices, routines, and automations.

    Example::

        agent = HomeAgent()
        ctx = AgentContext(user_id="papa", session_id="s1")
        response = await agent.handle("Licht im Wohnzimmer einschalten", ctx)
        print(response.text)
    """

    agent_id = "home"
    role = "smart_home"
    description = "Smart-Home Steuerung: Geräte, Routinen, Automationen"
    allowed_tools: List[str] = [
        "home_assistant",
        "mqtt_publish",
        "device_status",
        "routine_trigger",
    ]
    required_scope = "system"

    async def handle(self, intent: str, context: AgentContext) -> AgentResponse:
        """Handle a home-control intent.

        Args:
            intent:  User intent string (e.g. ``"Licht im Wohnzimmer einschalten"``).
            context: Request context.

        Returns:
            :class:`AgentResponse` describing the planned or executed action.
        """
        logger.info(
            "HomeAgent.handle: user_id=%s intent=%r",
            context.user_id,
            intent,
        )
        return AgentResponse(
            agent_id=self.agent_id,
            text=(
                f"Smart-Home Anfrage empfangen: \"{intent}\". "
                "Home-Automation-Integration wird ausgeführt."
            ),
            data={
                "intent": intent,
                "user_id": context.user_id,
                "session_id": context.session_id,
            },
        )

    async def can_handle(self, intent: str) -> bool:
        """Return True when *intent* contains home-related keywords.

        Args:
            intent: Natural-language intent string.

        Returns:
            True if the agent should handle this intent.
        """
        intent_lower = intent.lower()
        return any(kw in intent_lower for kw in _HOME_KEYWORDS)
