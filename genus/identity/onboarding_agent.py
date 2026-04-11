"""
OnboardingAgent — Phase 14

GENUS gets to know a new user via chat.
No form. No config file. A natural conversation.

Flow:

First start (no user known):
  GENUS: "Hallo! Ich bin GENUS.
          Ich weiß noch nicht wer du bist.
          Wie soll ich dich nennen?"

Known user, new device:
  GENUS: "Hey Ronny! Ich erkenne dein Token.
          Du bist auf einem neuen Gerät —
          soll ich das speichern?"

New family member (invited):
  GENUS: "Hallo! Ronny hat mir gesagt
          du könntest dazukommen.
          Ich bin GENUS — wer bist du?"
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.identity.group_store import GroupStore
from genus.identity.models import SystemRole, UserProfile
from genus.identity.profile_store import ProfileStore

logger = logging.getLogger(__name__)

TOPIC_ONBOARDING_STARTED = "identity.onboarding.started"
TOPIC_ONBOARDING_COMPLETED = "identity.onboarding.completed"


class OnboardingAgent(Agent):
    """Guides new users through the GENUS onboarding process via chat.

    Args:
        message_bus:   MessageBus for publishing events.
        profile_store: Where to persist the new UserProfile.
        group_store:   Where to create / join groups.
        llm_router:    Optional LLMRouter for natural-language replies.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        profile_store: ProfileStore,
        group_store: GroupStore,
        llm_router: Optional[Any] = None,
    ) -> None:
        super().__init__(
            agent_id="OnboardingAgent", name="OnboardingAgent"
        )
        self._bus = message_bus
        self._profiles = profile_store
        self._groups = group_store
        self._llm_router = llm_router
        # session_id → partial onboarding state
        self._sessions: Dict[str, Dict[str, Any]] = {}

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
        """Not used directly — interaction goes through start_onboarding / process_onboarding_message."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_onboarding(
        self,
        session_id: str,
        existing_token_user_id: Optional[str] = None,
    ) -> str:
        """Return the first greeting message and initialise session state."""
        if existing_token_user_id:
            profile = await self._profiles.get(existing_token_user_id)
            if profile:
                state: Dict[str, Any] = {
                    "step": "new_device",
                    "user_id": existing_token_user_id,
                    "display_name": profile.display_name,
                }
                self._sessions[session_id] = state
                return (
                    f"Hey {profile.display_name}! Ich erkenne dein Token. "
                    "Du bist auf einem neuen Gerät — soll ich das speichern?"
                )

        # Fresh start
        self._sessions[session_id] = {"step": "ask_name"}
        await self._bus.publish(Message(
            topic=TOPIC_ONBOARDING_STARTED,
            payload={"session_id": session_id},
            sender_id=self.id,
        ))
        return (
            "Hallo! Ich bin GENUS.\n"
            "Ich weiß noch nicht wer du bist.\n"
            "Wie soll ich dich nennen?"
        )

    async def process_onboarding_message(
        self,
        session_id: str,
        user_message: str,
    ) -> Tuple[str, bool]:
        """Process one onboarding message.

        Returns:
            ``(genus_response, onboarding_complete)``
        """
        if session_id not in self._sessions:
            # Start fresh if no state
            greeting = await self.start_onboarding(session_id)
            return greeting, False

        state = self._sessions[session_id]
        step = state.get("step", "ask_name")

        if step == "ask_name":
            return await self._handle_name_step(session_id, state, user_message)

        if step == "ask_group_type":
            return await self._handle_group_type_step(session_id, state, user_message)

        if step == "ask_language":
            return await self._handle_language_step(session_id, state, user_message)

        if step == "ask_style":
            return await self._handle_style_step(session_id, state, user_message)

        if step == "new_device":
            return await self._handle_new_device_step(session_id, state, user_message)

        # Unknown step — restart
        del self._sessions[session_id]
        greeting = await self.start_onboarding(session_id)
        return greeting, False

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------

    async def _handle_name_step(
        self, session_id: str, state: Dict, user_message: str
    ) -> Tuple[str, bool]:
        name = user_message.strip().split()[0] if user_message.strip() else user_message.strip()
        if not name:
            return "Ich habe deinen Namen nicht verstanden. Wie soll ich dich nennen?", False

        state["display_name"] = name
        state["step"] = "ask_group_type"
        return (
            f"Schön dich kennenzulernen, {name}! 😊\n"
            "Bist du alleine oder ist das für eine Familie / Gruppe?"
            " (Antworte z.B. mit 'alleine' oder 'Familie')"
        ), False

    async def _handle_group_type_step(
        self, session_id: str, state: Dict, user_message: str
    ) -> Tuple[str, bool]:
        lower = user_message.lower()
        if any(w in lower for w in ("allein", "solo", "nur ich")):
            state["group_type"] = "solo"
        else:
            state["group_type"] = "family"

        state["step"] = "ask_language"
        return (
            "Welche Sprache bevorzugst du? "
            "(z.B. 'Deutsch', 'Englisch', 'de', 'en')"
        ), False

    async def _handle_language_step(
        self, session_id: str, state: Dict, user_message: str
    ) -> Tuple[str, bool]:
        lang_map = {
            "deutsch": "de", "german": "de", "de": "de",
            "englisch": "en", "english": "en", "en": "en",
        }
        lang = lang_map.get(user_message.strip().lower(), "de")
        state["preferred_language"] = lang
        state["step"] = "ask_style"
        return (
            "Wie ausführlich soll ich antworten?\n"
            "'kurz' — kurz und präzise\n"
            "'ausführlich' — mehr Details\n"
            "'technisch' — technische Details"
        ), False

    async def _handle_style_step(
        self, session_id: str, state: Dict, user_message: str
    ) -> Tuple[str, bool]:
        lower = user_message.strip().lower()
        if "ausführ" in lower or "detail" in lower:
            style = "ausführlich"
        elif "tech" in lower:
            style = "technisch"
        else:
            style = "kurz"

        state["response_style"] = style

        # Create profile and group
        display_name = state.get("display_name", "Unbekannt")
        user_id = display_name.lower().replace(" ", "_")
        # Make user_id unique if it already exists
        base_id = user_id
        counter = 1
        while await self._profiles.exists(user_id):
            user_id = f"{base_id}_{counter}"
            counter += 1

        profile = UserProfile(
            user_id=user_id,
            display_name=display_name,
            preferred_language=state.get("preferred_language", "de"),
            response_style=style,
            system_role=SystemRole.ADULT,
            onboarding_complete=True,
        )
        await self._profiles.save(profile)

        # Group handling
        group_type = state.get("group_type", "family")
        if group_type == "family":
            group = await self._groups.get_or_create_default_family(
                admin_user_id=user_id
            )
            from genus.identity.models import GroupMember
            if not group.is_member(user_id):
                group.members.append(GroupMember(user_id=user_id, role="admin"))
                await self._groups.save(group)

        await self._bus.publish(Message(
            topic=TOPIC_ONBOARDING_COMPLETED,
            payload={"user_id": user_id, "session_id": session_id},
            sender_id=self.id,
        ))

        del self._sessions[session_id]

        return (
            f"Super! Willkommen, {display_name}! 🎉\n"
            "Ich habe dein Profil gespeichert. "
            "Von jetzt an kenne ich dich — lass uns loslegen!"
        ), True

    async def _handle_new_device_step(
        self, session_id: str, state: Dict, user_message: str
    ) -> Tuple[str, bool]:
        lower = user_message.strip().lower()
        user_id = state.get("user_id")
        display_name = state.get("display_name", "")

        if any(w in lower for w in ("ja", "yes", "klar", "ok", "sure")):
            # Nothing to persist for now — device detection is Phase 18.6
            del self._sessions[session_id]
            return (
                f"Gespeichert! Schön wieder da, {display_name}. 👋"
            ), True
        else:
            del self._sessions[session_id]
            return (
                f"Alright, {display_name}! Das Gerät bleibt unbekannt. "
                "Kein Problem — du bist trotzdem drin."
            ), True
