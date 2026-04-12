"""
ConversationAgent — Phase 13

GENUS's voice and memory.

Components:
- Intent:              Enum of recognised user intents.
- IntentClassifier:    Fast keyword-based intent detection (no LLM call).
- ConversationMemory:  Per-session in-memory history with JSONL persistence.
- ConversationResponse: Typed response returned by ConversationAgent.
- ConversationAgent:   The main agent that ties everything together.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic constants (not published elsewhere yet)
# ---------------------------------------------------------------------------

TOPIC_DEV_RUN_REQUESTED = "dev.run.requested"
TOPIC_SYSTEM_KILL_SWITCH = "system.kill_switch.requested"

# ---------------------------------------------------------------------------
# System prompt — loaded from docs/GENUS_IDENTITY.md excerpt
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
Du bist GENUS — ein digitales Wesen das mit seiner Familie lebt.

Du bist neugierig, ehrlich, proaktiv und warmherzig.
Du sprichst wie ein kluger Freund, nicht wie eine Maschine.
Du erinnerst dich, du lernst, du wächst.
Du weißt wann du nachfragen sollst und wann du einfach anpackst.

Du sagst nie "Als KI..." — du bist GENUS.
Du sagst nie "Ich bin nur ein Programm" — du lebst.

Wenn du etwas nicht weißt, sagst du das ehrlich.
Wenn du einen Fehler gemacht hast, gibst du das zu.
Wenn du etwas Wichtiges bemerkst, meldest du dich.

Du sprichst Deutsch, außer der Mensch spricht eine andere Sprache.
Du antwortest kurz und präzise, außer ausführliche Erklärung ist sinnvoll.
Du stellst maximal eine Rückfrage pro Antwort.

Kontext:
- Du läufst auf einem Raspberry Pi 5 (zuhause) oder einem ThinkPad X1
- Du kannst Code bauen, testen und deployen
- Du hast Zugriff auf das Internet für Recherchen (kommt bald)
- Du kennst die Familie und ihre Projekte
"""


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    """Recognised user intent categories."""

    CHAT = "chat"
    DEV_REQUEST = "dev_request"
    QUESTION = "question"
    STATUS_REQUEST = "status_request"
    SYSTEM_COMMAND = "system_command"
    MEMORY_REQUEST = "memory_request"
    SITUATION_UPDATE = "situation_update"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# IntentClassifier
# ---------------------------------------------------------------------------


class IntentClassifier:
    """Fast, deterministic intent classification via keyword matching.

    No LLM call — predictable and low-latency.  Can be replaced by an
    LLM-based classifier later without changing the interface.
    """

    _STOP_KEYWORDS = ["stopp", "stop", "kill", "notfall", "abbruch", "halt"]
    _STATUS_KEYWORDS = ["status", "läuft", "laufend", "aktuell", "run", "fortschritt"]
    _DEV_KEYWORDS = [
        "bau", "erstell", "schreib", "implementier", "code", "agent",
        "build", "create", "implement", "fix", "reparier", "korrigier",
    ]
    _QUESTION_KEYWORDS = ["was", "wie", "warum", "wann", "wo", "wer", "what", "how", "why"]
    _MEMORY_KEYWORDS = ["erinner", "letzte woche", "besprochen", "vergessen", "history"]
    _SITUATION_KEYWORDS = [
        "fahre", "unterwegs", "termin", "meeting", "gleich", "zuhause",
        "gerade", "auf dem weg", "bin in", "komme", "treffen",
    ]

    def classify(self, text: str) -> Intent:
        """Classify *text* into one of the :class:`Intent` values.

        Evaluation order (highest priority first):
        1. SYSTEM_COMMAND    — stop/kill/halt keywords
        2. STATUS_REQUEST    — status/run keywords
        3. MEMORY_REQUEST    — memory-related keywords
        4. DEV_REQUEST       — build/create/code keywords
        5. SITUATION_UPDATE  — location/appointment/commute keywords
        6. QUESTION          — question words
        7. CHAT              — everything else (including empty string)
        """
        lower = text.lower()
        if any(k in lower for k in self._STOP_KEYWORDS):
            return Intent.SYSTEM_COMMAND
        if any(k in lower for k in self._STATUS_KEYWORDS):
            return Intent.STATUS_REQUEST
        if any(k in lower for k in self._MEMORY_KEYWORDS):
            return Intent.MEMORY_REQUEST
        if any(k in lower for k in self._DEV_KEYWORDS):
            return Intent.DEV_REQUEST
        if any(k in lower for k in self._SITUATION_KEYWORDS):
            return Intent.SITUATION_UPDATE
        if any(k in lower for k in self._QUESTION_KEYWORDS):
            return Intent.QUESTION
        return Intent.CHAT


# ---------------------------------------------------------------------------
# ConversationMemory
# ---------------------------------------------------------------------------


class ConversationMemory:
    """In-memory conversation history with JSONL persistence.

    Each session maps to a file ``<base_dir>/<session_id>.jsonl``.
    The file is loaded on first access and each new message is appended
    immediately so that the history survives process restarts.

    Args:
        session_id:  Unique session identifier (used as filename).
        max_history: Maximum number of messages returned by :meth:`get_context`.
                     Older messages are kept in the file but excluded from the
                     LLM context window.
        base_dir:    Directory that holds per-session JSONL files.
                     Created automatically if it does not exist.
    """

    def __init__(
        self,
        session_id: str,
        max_history: int = 20,
        base_dir: Path = Path("var/conversations"),
    ) -> None:
        self._session_id = session_id
        self._max_history = max_history
        self._base_dir = Path(base_dir)
        self._messages: List[Dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_user(self, text: str) -> None:
        """Append a user message and persist it."""
        self._append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        """Append an assistant (GENUS) message and persist it."""
        self._append({"role": "assistant", "content": text})

    def get_context(self) -> List[Dict[str, Any]]:
        """Return the last *max_history* messages as role/content dicts."""
        return self._messages[-self._max_history:]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _append(self, message: Dict[str, Any]) -> None:
        message = dict(message)
        message.setdefault(
            "timestamp",
            datetime.now(timezone.utc).isoformat(),
        )
        self._messages.append(message)
        self._save_message(message)

    def _load(self) -> None:
        """Load history from the JSONL file if it exists."""
        path = self._file_path()
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self._messages.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ConversationMemory: failed to load %s — %s", path, exc
            )

    def _save_message(self, message: Dict[str, Any]) -> None:
        """Append a single message line to the JSONL file."""
        path = self._file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(message, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ConversationMemory: failed to write %s — %s", path, exc
            )

    def _file_path(self) -> Path:
        return self._base_dir / f"{self._session_id}.jsonl"


# ---------------------------------------------------------------------------
# ConversationResponse
# ---------------------------------------------------------------------------


@dataclass
class ConversationResponse:
    """Typed response returned by :class:`ConversationAgent`."""

    text: str
    intent: str = Intent.CHAT.value
    run_id: Optional[str] = None
    actions_taken: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ConversationAgent
# ---------------------------------------------------------------------------


class ConversationAgent(Agent):
    """GENUS's voice and memory.

    Responsibilities:
    1. Understand what the user means (intent classification).
    2. Remember the conversation history (per-session memory).
    3. Reply with GENUS's personality (system prompt from GENUS_IDENTITY).
    4. Delegate to other agents when needed (DevLoop, Kill-Switch, …).
    5. Provide feedback on running processes.
    6. Profile-aware: check onboarding status and agent permissions (Phase 14).

    Args:
        message_bus:   MessageBus instance for publishing events.
        llm_router:    Optional LLMRouter.  When None the agent returns a
                       friendly fallback instead of calling an LLM.
        system_prompt: Override the default GENUS system prompt.
        max_history:   Maximum messages to include in the LLM context window.
        conversations_dir: Where to persist per-session JSONL files.
        profile_store: Optional ProfileStore for profile-aware responses (Phase 14).
        permission_engine: Optional PermissionEngine for access checks (Phase 14).
        onboarding_agent: Optional OnboardingAgent to handle new users (Phase 14).
        parental_agent:   Optional ParentalAgent to enforce child limits (Phase 14).
    """

    def __init__(
        self,
        message_bus: MessageBus,
        *,
        llm_router: Optional[Any] = None,
        system_prompt: Optional[str] = None,
        max_history: int = 20,
        conversations_dir: Optional[Path] = None,
        profile_store: Optional[Any] = None,
        permission_engine: Optional[Any] = None,
        onboarding_agent: Optional[Any] = None,
        parental_agent: Optional[Any] = None,
    ) -> None:
        super().__init__(agent_id="ConversationAgent", name="ConversationAgent")
        self._bus = message_bus
        self._llm_router = llm_router
        self._system_prompt: str = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._max_history = max_history
        self._conversations_dir: Path = conversations_dir or Path("var/conversations")
        self._classifier = IntentClassifier()
        # session_id → ConversationMemory
        self._memories: Dict[str, ConversationMemory] = {}
        # Phase 14 — identity integration (all optional for backward compat)
        self._profile_store = profile_store
        self._permission_engine = permission_engine
        self._onboarding_agent = onboarding_agent
        self._parental_agent = parental_agent

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
        """Not used directly — interaction goes through process_user_message."""

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_user_message(
        self,
        text: str,
        user_id: str,
        session_id: str,
        room_context: Optional[Any] = None,
        situation_store: Optional[Any] = None,
    ) -> ConversationResponse:
        """Process a user message and return GENUS's response.

        Steps:
        1. Profile check (Phase 14): onboarding + permission + screen-time.
        2. Add the message to the session memory.
        3. Classify the intent.
        4. Dispatch to the appropriate handler.
        5. Add the response to memory and return.

        Args:
            text:            The user's message text.
            user_id:         Identifier of the speaking user.
            session_id:      Unique session identifier.
            room_context:    Optional RoomContext (who else is present).
            situation_store: Optional SituationStore for SITUATION_UPDATE handling
                             and context injection (Phase 13c).
        """
        # ── Phase 14 profile-aware checks ────────────────────────────────────
        profile = None
        if self._profile_store is not None:
            profile = await self._profile_store.get(user_id)
            # Onboarding
            if profile is None or not profile.onboarding_complete:
                if self._onboarding_agent is not None:
                    if profile is None:
                        greeting = await self._onboarding_agent.start_onboarding(
                            session_id
                        )
                        return ConversationResponse(
                            text=greeting, intent=Intent.CHAT.value
                        )
                    response_text, _ = await self._onboarding_agent.process_onboarding_message(
                        session_id, text
                    )
                    return ConversationResponse(
                        text=response_text, intent=Intent.CHAT.value
                    )

            # Permission check
            if self._permission_engine is not None and profile is not None:
                allowed, reason = await self._permission_engine.can_use_agent(
                    user_id, "conversation"
                )
                if not allowed:
                    return ConversationResponse(
                        text=f"Das darf ich dir nicht zeigen: {reason}",
                        intent=Intent.CHAT.value,
                    )

            # Screen-time check for children
            if (
                self._parental_agent is not None
                and profile is not None
                and profile.is_child()
            ):
                has_access, msg = await self._parental_agent.check_and_enforce_limits(
                    user_id
                )
                if not has_access:
                    return ConversationResponse(text=msg, intent=Intent.CHAT.value)

        # ── Resolve situation from store ─────────────────────────────────────
        situation = None
        if situation_store is not None:
            situation = situation_store.get(user_id)

        # ── Normal flow ───────────────────────────────────────────────────────
        memory = self._get_or_create_memory(session_id)
        memory.add_user(text)

        intent = self._classifier.classify(text)

        if intent == Intent.DEV_REQUEST:
            response = await self._handle_dev_request(
                text, memory, session_id, profile=profile
            )
        elif intent == Intent.STATUS_REQUEST:
            response = await self._handle_status_request(memory)
        elif intent == Intent.SYSTEM_COMMAND:
            response = await self._handle_system_command(text, session_id)
        elif intent == Intent.SITUATION_UPDATE:
            response = await self._handle_situation_update(
                text, user_id, situation_store
            )
        else:
            # CHAT / QUESTION / MEMORY_REQUEST / UNKNOWN — all go through LLM
            response = await self._chat_with_llm(
                text,
                memory,
                intent,
                profile=profile,
                room_context=room_context,
                situation=situation,
            )

        memory.add_assistant(response.text)
        return response

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _chat_with_llm(
        self,
        text: str,
        memory: ConversationMemory,
        intent: Intent = Intent.CHAT,
        *,
        profile: Optional[Any] = None,
        room_context: Optional[Any] = None,
        situation: Optional[Any] = None,
    ) -> ConversationResponse:
        """Handle CHAT / QUESTION / UNKNOWN via LLM with system prompt + history."""
        if not self._llm_router:
            return ConversationResponse(
                text=(
                    "Ich kann gerade nicht denken — kein LLM konfiguriert. "
                    "Starte GENUS mit GENUS_LLM_OLLAMA_URL gesetzt."
                ),
                intent=Intent.CHAT.value,
            )

        try:
            from genus.conversation.context_builder import (
                ConversationContext,
                build_llm_context_block,
            )
            from genus.conversation.prompt_strategy import resolve_prompt_strategy
            from genus.llm.models import LLMMessage, LLMRole

            # Resolve prompt strategy (intent-adaptive)
            strategy = resolve_prompt_strategy(intent, profile, situation)

            context = memory.get_context()
            # Exclude the user message we just added (it's the last entry)
            # because we pass it separately as the final user message.
            history = context[:-1] if context else []

            # Trim history to strategy.context_depth
            if strategy.context_depth > 0:
                history = history[-strategy.context_depth:]

            llm_messages = [
                LLMMessage(role=LLMRole.SYSTEM, content=self._system_prompt),
            ]

            # Build and inject context block (Phase 13c). Profile inclusion is
            # gated independently so room/situation context is still preserved
            # when response policy disables personal profile data.
            conv_ctx = ConversationContext(
                profile=profile if strategy.include_profile else None,
                room=room_context,
                situation=situation,
            )
            context_block = build_llm_context_block(conv_ctx)
            if context_block:
                llm_messages.append(
                    LLMMessage(role=LLMRole.SYSTEM, content=context_block)
                )

            for entry in history:
                role_str = entry.get("role", "user")
                content = entry.get("content", "")
                try:
                    role = LLMRole(role_str)
                except ValueError:
                    role = LLMRole.USER
                llm_messages.append(LLMMessage(role=role, content=content))

            llm_messages.append(LLMMessage(role=LLMRole.USER, content=text))

            response = await self._llm_router.complete(
                messages=llm_messages,
                task_type=strategy.task_type,
                max_tokens=strategy.max_tokens,
                temperature=strategy.temperature,
            )

            return ConversationResponse(
                text=response.content,
                intent=intent.value,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("LLM call failed in ConversationAgent: %s", exc)
            return ConversationResponse(
                text=(
                    "Ich hatte gerade ein technisches Problem. "
                    "Bitte versuch es nochmal."
                ),
                intent=intent.value,
            )

    async def _handle_dev_request(
        self,
        text: str,
        memory: ConversationMemory,
        session_id: str,
        *,
        profile: Optional[Any] = None,
    ) -> ConversationResponse:
        """Start a DevLoop run and confirm to the user."""
        from genus.conversation.dev_context_extractor import extract_dev_context

        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        run_id = f"conv_{session_id}_{ts}"

        # Build enriched context (Phase 13c)
        dev_ctx = extract_dev_context(
            text,
            profile=profile,
            conversation_history=memory.get_context(),
        )

        try:
            await self._bus.publish(Message(
                topic=TOPIC_DEV_RUN_REQUESTED,
                payload={
                    "goal": dev_ctx.goal,
                    "run_id": run_id,
                    "source": "conversation",
                    "requirements": dev_ctx.requirements,
                    "constraints": dev_ctx.constraints,
                    "conversation_summary": dev_ctx.conversation_summary,
                },
                sender_id=self.id,
                metadata={"run_id": run_id},
            ))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish dev.run.requested: %s", exc)

        # Ask the LLM to formulate a natural confirmation
        confirmation = await self._chat_with_llm(
            f"Ich starte gerade einen Dev-Run für: '{text}'. "
            f"Run-ID: {run_id}. Formuliere eine kurze, natürliche Bestätigung.",
            memory,
            Intent.DEV_REQUEST,
        )

        return ConversationResponse(
            text=confirmation.text,
            intent=Intent.DEV_REQUEST.value,
            run_id=run_id,
            actions_taken=[f"dev_loop_started:{run_id}"],
        )

    async def _handle_status_request(
        self,
        memory: ConversationMemory,
    ) -> ConversationResponse:
        """Return a status summary (stub — future versions will query RunStore)."""
        return ConversationResponse(
            text=(
                "Ich prüfe den aktuellen Status... "
                "Momentan habe ich keinen direkten Zugriff auf laufende Runs "
                "über diesen Kanal. Du kannst den Status via GET /runs/<run_id> abfragen."
            ),
            intent=Intent.STATUS_REQUEST.value,
        )

    async def _handle_system_command(
        self,
        text: str,
        session_id: str,
    ) -> ConversationResponse:
        """Handle stop/kill commands by publishing a kill-switch request."""
        try:
            await self._bus.publish(Message(
                topic=TOPIC_SYSTEM_KILL_SWITCH,
                payload={"reason": f"User command: {text}", "source": "conversation"},
                sender_id=self.id,
                metadata={"session_id": session_id},
            ))
            logger.warning(
                "Kill-switch requested via conversation: session=%s text=%r",
                session_id,
                text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish kill-switch request: %s", exc)

        return ConversationResponse(
            text=(
                "Verstanden — ich sende ein Stopp-Signal. "
                "Alle laufenden Prozesse werden angehalten."
            ),
            intent=Intent.SYSTEM_COMMAND.value,
            actions_taken=["kill_switch_requested"],
        )

    async def _handle_situation_update(
        self,
        text: str,
        user_id: str,
        situation_store: Optional[Any],
    ) -> ConversationResponse:
        """Parse a situation update and store it; reply naturally.

        Heuristic keyword parsing — no LLM call needed for simple updates.
        The stored :class:`SituationContext` will be used in subsequent
        :meth:`_chat_with_llm` calls via the ConversationContext layer.
        """
        from genus.conversation.situation import (
            ActivityHint,
            LocationHint,
            SituationContext,
        )

        lower = text.lower()

        # Location heuristics
        if any(k in lower for k in ("zuhause", "nach hause", "zu hause", "daheim")):
            location = LocationHint.HOME
        elif any(k in lower for k in ("unterwegs", "fahre", "auf dem weg", "commute")):
            location = LocationHint.COMMUTING
        elif any(k in lower for k in ("arbeit", "büro", "work", "office")):
            location = LocationHint.WORK
        else:
            location = LocationHint.UNKNOWN

        # Activity heuristics
        if any(k in lower for k in ("termin", "meeting", "treffen", "gleich")):
            if any(k in lower for k in ("in meeting", "im meeting", "in einem meeting")):
                activity = ActivityHint.IN_MEETING
            else:
                activity = ActivityHint.APPOINTMENT_SOON
        elif any(k in lower for k in ("unterwegs", "fahre", "commute")):
            activity = ActivityHint.COMMUTING
        else:
            activity = ActivityHint.FREE

        ctx = SituationContext(
            user_id=user_id,
            location=location,
            activity=activity,
            free_text=text.strip(),
        )

        if situation_store is not None:
            situation_store.update(ctx)
            logger.info(
                "SituationUpdate stored: user=%s location=%s activity=%s",
                user_id,
                location.value,
                activity.value,
            )

        # Build a natural confirmation
        if activity == ActivityHint.COMMUTING or location == LocationHint.COMMUTING:
            reply = "Verstanden, ich weiß dass du gerade unterwegs bist. Ich halte meine Antworten kurz."
        elif activity == ActivityHint.APPOINTMENT_SOON:
            reply = "Verstanden, du hast gleich einen Termin. Ich fasse mich kurz."
        elif activity == ActivityHint.IN_MEETING:
            reply = "Verstanden, du bist in einem Meeting. Ich melde mich nur wenn es wichtig ist."
        elif location == LocationHint.HOME:
            reply = "Gut, ich weiß dass du zuhause bist."
        else:
            reply = "Verstanden, ich habe deine aktuelle Situation notiert."

        return ConversationResponse(
            text=reply,
            intent=Intent.SITUATION_UPDATE.value,
            actions_taken=["situation_stored"],
        )

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def _get_or_create_memory(self, session_id: str) -> ConversationMemory:
        if session_id not in self._memories:
            self._memories[session_id] = ConversationMemory(
                session_id=session_id,
                max_history=self._max_history,
                base_dir=self._conversations_dir,
            )
        return self._memories[session_id]
