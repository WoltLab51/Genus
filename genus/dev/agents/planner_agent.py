"""
Planner Agent

Subscribes to dev.plan.requested and publishes dev.plan.completed or
dev.plan.failed.

Supports optional LLM-based planning via an LLMRouter. Without an
llm_router the agent falls back to a deterministic placeholder plan.
"""

import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase

logger = logging.getLogger(__name__)

_STUB_STEPS = [
    "Step 1: Analyze requirements",
    "Step 2: Design solution architecture",
    "Step 3: Implement core functionality",
    "Step 4: Add tests and documentation",
]


class PlannerAgent(DevAgentBase):
    """Agent that responds to planning requests.

    Args:
        bus:         MessageBus instance.
        agent_id:    Unique identifier for this agent.
        mode:        Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:  If mode=="fail" and topic matches, publish failed response.
        llm_router:  Optional LLMRouter. When provided the agent uses the LLM
                     to generate a plan. When None, stub behaviour is used
                     (backward compatible).

    Example::

        planner = PlannerAgent(bus, "planner-1", mode="ok")
        planner.start()
        # ... orchestrator publishes dev.plan.requested ...
        # ... planner responds with dev.plan.completed ...
        planner.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "PlannerAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
        llm_router: Optional[Any] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._llm_router = llm_router

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.plan.requested."""
        return [(topics.DEV_PLAN_REQUESTED, self._handle_plan_requested)]

    async def _handle_plan_requested(self, msg: Message) -> None:
        """Handle dev.plan.requested messages."""
        # Validate metadata
        run_id = msg.metadata.get("run_id")
        if not run_id:
            return

        # Validate payload
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return

        # Check if we should simulate failure
        should_fail = (
            self._mode == "fail"
            and (self._fail_topic is None or self._fail_topic == msg.topic)
        )

        if should_fail:
            # Publish failed response
            await self._bus.publish(
                events.dev_plan_failed_message(
                    run_id,
                    self.agent_id,
                    "Planning failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Extract request data
        requirements: List[str] = msg.payload.get("requirements", [])
        constraints: List[str] = msg.payload.get("constraints", [])
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        agent_spec_template: Optional[Dict[str, Any]] = metadata.get("agent_spec_template")
        domain: Optional[str] = metadata.get("domain")

        # ── Stellschraube 3: EpisodicContext → PlannerPrompt (Phase 13c) ────
        episodic_context = msg.payload.get("episodic_context")
        episodic_summary: Optional[str] = None
        if episodic_context:
            from genus.dev.context_formatter import format_episodic_for_planner
            episodic_summary = format_episodic_for_planner(episodic_context)

        # Generate plan
        if self._llm_router is not None:
            llm_result = await self._generate_plan_with_llm(
                requirements, constraints, agent_spec_template, domain,
                episodic_summary=episodic_summary,
            )
        else:
            llm_result = None

        if llm_result is not None:
            steps = llm_result.get("steps", _STUB_STEPS)
            plan_summary = llm_result.get("plan_summary", "")
        else:
            steps = list(_STUB_STEPS)
            plan_summary = ""

        # Build plan artifact
        plan: Dict[str, Any] = {
            "steps": steps,
            "acceptance_criteria": list(requirements) if requirements else ["All tests pass"],
            "risks": self._derive_risks(constraints),
        }
        if plan_summary:
            plan["plan_summary"] = plan_summary

        # Publish completed response
        await self._bus.publish(
            events.dev_plan_completed_message(
                run_id,
                self.agent_id,
                plan,
                phase_id=phase_id,
            )
        )

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def _generate_plan_with_llm(
        self,
        requirements: List[str],
        constraints: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
        domain: Optional[str],
        *,
        episodic_summary: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Call the LLM router and return parsed plan data, or None on error."""
        from genus.llm.exceptions import LLMProviderUnavailableError, LLMResponseParseError
        from genus.llm.router import TaskType

        try:
            messages = self._build_plan_prompt(
                requirements, constraints, agent_spec_template, domain,
                episodic_summary=episodic_summary,
            )
            response = await self._llm_router.complete(
                messages, task_type=TaskType.PLANNING
            )
            return self._parse_plan_response(response.content)
        except LLMResponseParseError as exc:
            logger.warning("PlannerAgent: LLM response parse error, using fallback: %s", exc)
            return {"steps": ["implement as specified"], "plan_summary": "LLM parse error, using fallback"}
        except LLMProviderUnavailableError as exc:
            logger.warning("PlannerAgent: LLM provider unavailable, using stub: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("PlannerAgent: unexpected LLM error, using stub: %s", exc)
            return None

    def _build_plan_prompt(
        self,
        requirements: List[str],
        constraints: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
        domain: Optional[str],
        *,
        episodic_summary: Optional[str] = None,
    ) -> List[Any]:
        """Build the list of LLMMessages for the planning prompt."""
        from genus.llm.models import LLMMessage, LLMRole

        system = (
            "Du bist ein erfahrener Software-Architekt im GENUS-System.\n"
            "Deine Aufgabe: Erstelle einen konkreten, umsetzbaren Implementierungsplan.\n\n"
            "Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt in diesem Format:\n"
            '{\n'
            '  "steps": ["Schritt 1: ...", "Schritt 2: ...", "Schritt 3: ..."],\n'
            '  "plan_summary": "Kurze Zusammenfassung des Plans"\n'
            '}\n\n'
            "Keine weiteren Erklärungen, kein Markdown, nur das JSON-Objekt."
        )

        messages: List[Any] = [LLMMessage(role=LLMRole.SYSTEM, content=system)]

        # ── EpisodicContext as additional SYSTEM message (Phase 13c) ─────────
        if episodic_summary:
            messages.append(LLMMessage(role=LLMRole.SYSTEM, content=episodic_summary))

        user_parts = []
        if domain:
            user_parts.append(f"Domain: {domain}")
        if agent_spec_template:
            name = agent_spec_template.get("name", "UnknownAgent")
            desc = agent_spec_template.get("description", "")
            spec_topics = agent_spec_template.get("topics", [])
            user_parts.append(f"Ziel-Agent: {name}")
            if desc:
                user_parts.append(f"Beschreibung: {desc}")
            if spec_topics:
                user_parts.append(f"Topics: {', '.join(spec_topics)}")
        if requirements:
            user_parts.append(
                "Anforderungen:\n" + "\n".join(f"- {r}" for r in requirements)
            )
        if constraints:
            user_parts.append(
                "Einschränkungen:\n" + "\n".join(f"- {c}" for c in constraints)
            )

        messages.append(LLMMessage(role=LLMRole.USER, content="\n\n".join(user_parts)))
        return messages

    def _parse_plan_response(self, content: str) -> Dict[str, Any]:
        """Parse the LLM response as JSON.

        Robust against markdown code fences and leading/trailing whitespace.

        Raises:
            LLMResponseParseError: when no valid JSON is found.
        """
        from genus.llm.exceptions import LLMResponseParseError

        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMResponseParseError(
                f"PlannerAgent: invalid JSON response: {exc}"
            ) from exc

        return {
            "steps": data.get("steps", []),
            "plan_summary": data.get("plan_summary", ""),
        }

    def _derive_risks(self, constraints: List[str]) -> List[str]:
        """Derive placeholder risks from constraints."""
        if not constraints:
            return []
        return [f"Risk: constraint '{c}' may be violated" for c in constraints[:2]]
