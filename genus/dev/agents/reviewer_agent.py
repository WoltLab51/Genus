"""
Reviewer Agent

Subscribes to dev.review.requested and publishes dev.review.completed or
dev.review.failed.

Phase 10d: Supports optional LLM-based code review via LLMRouter, with a
score-feedback loop so GENUS learns which provider performs best.

Without an llm_router the agent falls back to deterministic stub behaviour
(backward-compatible with existing integration tests that use review_profile).
"""

import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase

logger = logging.getLogger(__name__)

# Patterns that indicate dangerous code (security check)
_SECURITY_PATTERNS = [
    "eval(",
    "exec(",
    "os.system(",
    "subprocess.call(",
    "subprocess.run(",
    "__import__(",
]

_FALLBACK_REVIEW: Dict[str, Any] = {
    "approved": True,
    "score": 0.75,
    "issues": [],
    "suggestions": [],
    "summary": "LLM review unavailable, auto-approved",
}


class ReviewerAgent(DevAgentBase):
    """Agent that responds to review requests.

    Supports two operating modes:

    1. **Legacy / profile-based** (no ``llm_router`` + no ``code`` in payload):
       Returns a deterministic review based on ``review_profile``.  Used by
       integration tests and the existing DevLoopOrchestrator.

    2. **LLM-based** (``code`` present in payload):
       Calls the LLMRouter with ``TaskType.CODE_REVIEW``, parses the JSON
       response, applies a security check, enforces ``score < 0.5 →
       approved=False``, and writes experience scores back to the router.

    Args:
        bus:            MessageBus instance.
        agent_id:       Unique identifier for this agent.
        mode:           Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:     If mode=="fail" and topic matches, publish failed response.
        review_profile: Review profile: "clean" (no issues) or "high_sev"
                        (high severity finding).  Only used when no ``code`` is
                        present in the payload (legacy path).
        llm_router:     Optional LLMRouter.  When provided the agent uses the
                        LLM to review code.  When None, stub behaviour is used.

    Example::

        # Clean review (backward compatible, no LLM)
        reviewer = ReviewerAgent(bus, "reviewer-1", review_profile="clean")
        reviewer.start()

        # LLM-based review with score feedback
        reviewer = ReviewerAgent(bus, "reviewer-1", llm_router=router)
        reviewer.start()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "ReviewerAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
        review_profile: Literal["clean", "high_sev"] = "clean",
        *,
        llm_router: Optional[Any] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._review_profile = review_profile
        self._llm_router = llm_router

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.review.requested."""
        return [(topics.DEV_REVIEW_REQUESTED, self._handle_review_requested)]

    async def _handle_review_requested(self, msg: Message) -> None:
        """Handle dev.review.requested messages."""
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
            await self._bus.publish(
                events.dev_review_failed_message(
                    run_id,
                    self.agent_id,
                    "Review failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # If 'code' is in the payload, use LLM-based review (Phase 10d path)
        code = msg.payload.get("code")
        if code is not None:
            review = await self._perform_code_review(msg, run_id, code)
        else:
            # Legacy path: deterministic profile-based review
            review = self._build_review()

        await self._bus.publish(
            events.dev_review_completed_message(
                run_id,
                self.agent_id,
                review,
                phase_id=phase_id,
            )
        )

    # ------------------------------------------------------------------
    # LLM-based code review (Phase 10d)
    # ------------------------------------------------------------------

    async def _perform_code_review(
        self, msg: Message, run_id: str, code: str
    ) -> Dict[str, Any]:
        """Orchestrate the LLM-based code review including score feedback."""
        payload = msg.payload if isinstance(msg.payload, dict) else {}
        filename: str = payload.get("filename", "unknown.py")
        plan: Dict[str, Any] = payload.get("plan") or {}
        plan_steps: List[str] = plan.get("steps", [])
        inner_metadata: Dict[str, Any] = payload.get("metadata") or {}
        agent_spec_template: Optional[Dict[str, Any]] = (
            inner_metadata.get("agent_spec_template")
            or msg.metadata.get("agent_spec_template")
        )
        # run_id for score records (may differ from message run_id)
        score_run_id: Optional[str] = inner_metadata.get("run_id") or run_id
        builder_provider: Optional[str] = inner_metadata.get("provider_name")

        # Security check — short-circuit before calling LLM
        security_issues = self._check_security(code)
        if security_issues:
            review: Dict[str, Any] = {
                "approved": False,
                "score": 0.0,
                "issues": security_issues,
                "suggestions": [],
                "summary": "Security issues detected, code rejected.",
            }
            if self._llm_router is not None and builder_provider:
                from genus.llm.router import TaskType

                await self._llm_router.record_score(
                    provider_name=builder_provider,
                    task_type=TaskType.CODE_GEN,
                    score=0.0,
                    run_id=score_run_id,
                    metadata={"filename": filename, "approved": False},
                )
            return review

        # LLM review
        if self._llm_router is not None:
            review = await self._review_with_llm(
                code,
                filename,
                plan_steps,
                agent_spec_template,
                builder_provider,
                score_run_id,
            )
        else:
            review = dict(_FALLBACK_REVIEW)

        # Enforce: score < 0.5 → approved = False
        if review.get("score", 0.75) < 0.5:
            review["approved"] = False

        return review

    async def _review_with_llm(
        self,
        code: str,
        filename: str,
        plan_steps: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
        builder_provider: Optional[str],
        run_id: Optional[str],
    ) -> Dict[str, Any]:
        """Call the LLM router and record scores for the feedback loop."""
        from genus.llm.router import TaskType

        try:
            messages = self._build_review_prompt(code, filename, plan_steps, agent_spec_template)
            llm_response = await self._llm_router.complete(
                messages, task_type=TaskType.CODE_REVIEW
            )
            review = self._parse_review_response(llm_response.content)

            # Score-feedback loop — let the router learn
            if builder_provider:
                await self._llm_router.record_score(
                    provider_name=builder_provider,
                    task_type=TaskType.CODE_GEN,
                    score=review["score"],
                    run_id=run_id,
                    metadata={"filename": filename, "approved": review["approved"]},
                )
            await self._llm_router.record_score(
                provider_name=llm_response.provider,
                task_type=TaskType.CODE_REVIEW,
                score=review["score"],
                run_id=run_id,
            )

            return review

        except Exception as exc:  # noqa: BLE001
            logger.warning("ReviewerAgent: LLM review failed, using fallback: %s", exc)
            return dict(_FALLBACK_REVIEW)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _build_review_prompt(
        self,
        code: str,
        filename: str,
        plan_steps: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
    ) -> List[Any]:
        """Build the list of LLMMessages for the code-review prompt."""
        from genus.llm.models import LLMMessage, LLMRole

        system = (
            "Du bist ein erfahrener Python Code-Reviewer im GENUS-System.\n"
            "Prüfe den Code auf:\n"
            "1. Korrektheit (läuft er fehlerfrei?)\n"
            "2. GENUS-Architektur (erbt von Agent, korrekte Lifecycle-Methoden?)\n"
            "3. Sicherheit (keine gefährlichen Aufrufe wie eval, exec, os.system?)\n"
            "4. Vollständigkeit (sind alle Plan-Schritte umgesetzt?)\n\n"
            "Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt:\n"
            "{\n"
            '  "approved": true/false,\n'
            '  "score": 0.0-1.0,\n'
            '  "issues": ["Problem 1", "Problem 2"],\n'
            '  "suggestions": ["Verbesserung 1"],\n'
            '  "summary": "Kurze Bewertung"\n'
            "}\n\n"
            "score 0.9-1.0: exzellent, 0.7-0.9: gut, 0.5-0.7: akzeptabel, <0.5: abgelehnt\n"
            "approved=false wenn score < 0.5 oder kritische Sicherheitsprobleme vorhanden."
        )

        user_parts = []
        if agent_spec_template:
            name = agent_spec_template.get("name", "UnknownAgent")
            user_parts.append(f"Erwarteter Agent: {name}")
        if plan_steps:
            user_parts.append("Plan-Schritte:\n" + "\n".join(f"- {s}" for s in plan_steps))
        user_parts.append(f"Datei: {filename}\n\nCode:\n{code}")

        return [
            LLMMessage(role=LLMRole.SYSTEM, content=system),
            LLMMessage(role=LLMRole.USER, content="\n\n".join(user_parts)),
        ]

    def _parse_review_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM review JSON response with fallback defaults on error.

        Strips markdown fences if present before parsing.
        """
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return dict(_FALLBACK_REVIEW)

        return {
            "approved": bool(data.get("approved", True)),
            "score": float(data.get("score", 0.75)),
            "issues": list(data.get("issues", [])),
            "suggestions": list(data.get("suggestions", [])),
            "summary": str(data.get("summary", "")),
        }

    def _check_security(self, code: str) -> List[str]:
        """Return a list of security issue descriptions found in ``code``.

        Returns an empty list if the code is safe.
        """
        return [
            f"Dangerous pattern detected: {pattern}"
            for pattern in _SECURITY_PATTERNS
            if pattern in code
        ]

    # ------------------------------------------------------------------
    # Legacy profile-based review (backward compatible)
    # ------------------------------------------------------------------

    def _build_review(self) -> Dict[str, Any]:
        """Build review artifact based on review_profile."""
        if self._review_profile == "high_sev":
            return {
                "findings": [
                    {
                        "severity": "high",
                        "message": "Potential security vulnerability detected (placeholder)",
                        "location": "genus/example.py:42",
                    }
                ],
                "severity": "high",
                "required_fixes": ["Address security vulnerability"],
            }
        else:  # clean
            return {
                "findings": [],
                "severity": "none",
                "required_fixes": [],
            }
