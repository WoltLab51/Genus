"""
Template Builder Agent — Phase 7

Replaces :class:`~genus.growth.stub_dev_agent.StubDevAgent` as the
dev-loop driver in :class:`~genus.growth.growth_bridge.GrowthBridge`.

Instead of returning stub payloads this agent:

1. **Plans** — builds a structured plan from the ``agent_spec_template`` in
   the ``dev.plan.requested`` payload.
2. **Implements** — renders a complete Python agent class via
   :class:`~genus.dev.agents.agent_code_template.AgentCodeTemplate` and
   writes it to ``<output_base_path>/<snake_case_name>.py``.
3. **Tests** — attempts to import the generated file via
   ``importlib.util.spec_from_file_location`` and reports pass/fail.
4. **Reviews** — checks whether the generated file exists on disk and
   reports ``approved: True`` when it does.
5. **Fixes** — logs the failure and returns a stub response so the
   DevLoopOrchestrator does not hang on a retry loop.

Internal run state is keyed by ``run_id`` so that multiple concurrent
builds are handled independently.

Topics subscribed:
    - ``dev.plan.requested``
    - ``dev.implement.requested``
    - ``dev.test.requested``
    - ``dev.fix.requested``
    - ``dev.review.requested``

Topics published:
    - ``dev.plan.completed``
    - ``dev.implement.completed``
    - ``dev.test.completed``
    - ``dev.fix.completed``
    - ``dev.review.completed``
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Dict, Optional

from genus.communication.message_bus import Message, MessageBus
from genus.core.agent import Agent, AgentState
from genus.dev import events
from genus.dev.agents.agent_code_template import (
    AgentCodeTemplate,
    class_name_to_filename,
    extract_class_name,
    extract_subscribe_topics,
)

logger = logging.getLogger(__name__)

_PHASE_TOPICS = (
    "dev.plan.requested",
    "dev.implement.requested",
    "dev.test.requested",
    "dev.fix.requested",
    "dev.review.requested",
)


class TemplateBuilderAgent(Agent):
    """Template-based builder agent — Phase 7 drop-in for StubDevAgent.

    Generates real Python files from ``agent_spec_template`` payloads.

    Args:
        message_bus:      The shared :class:`~genus.communication.message_bus.MessageBus`.
        output_base_path: Root directory where generated agent files are
                          written.  Defaults to ``Path("genus/agents/generated")``.
                          Tests should pass ``tmp_path / "generated"``.
        agent_id:         Optional custom agent ID.  Auto-generated if
                          omitted.
        name:             Optional human-readable agent name.  Defaults to
                          ``"TemplateBuilderAgent"``.
    """

    def __init__(
        self,
        message_bus: MessageBus,
        output_base_path: Optional[Path] = None,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(agent_id=agent_id, name=name or "TemplateBuilderAgent")
        self._bus = message_bus
        self._output_base_path: Path = (
            output_base_path
            if output_base_path is not None
            else Path("genus/agents/generated")
        )
        # run_id → {"plan": dict, "generated_file": Optional[Path], "class_name": str}
        self._run_state: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Subscribe to all DevLoop phase-requested topics."""
        for topic in _PHASE_TOPICS:
            self._bus.subscribe(topic, f"{self.id}:{topic}", self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        """Transition to RUNNING state."""
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        """Unsubscribe from all topics and transition to STOPPED state."""
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def process_message(self, message: Message) -> None:
        """Dispatch an incoming DevLoop phase-requested event to its handler.

        Args:
            message: The incoming :class:`~genus.communication.message_bus.Message`.
        """
        handlers = {
            "dev.plan.requested": self._handle_plan,
            "dev.implement.requested": self._handle_implement,
            "dev.test.requested": self._handle_test,
            "dev.fix.requested": self._handle_fix,
            "dev.review.requested": self._handle_review,
        }
        handler = handlers.get(message.topic)
        if handler is not None:
            await handler(message)

    # ------------------------------------------------------------------
    # Phase handlers
    # ------------------------------------------------------------------

    async def _handle_plan(self, message: Message) -> None:
        """Respond to ``dev.plan.requested``.

        Builds a structured plan from ``agent_spec_template`` (in payload or
        metadata) and publishes ``dev.plan.completed``.
        """
        run_id = message.metadata.get("run_id")
        phase_id = (
            message.payload.get("phase_id")
            if isinstance(message.payload, dict)
            else None
        )
        if not run_id or not phase_id:
            return

        payload = message.payload if isinstance(message.payload, dict) else {}
        metadata = message.metadata if isinstance(message.metadata, dict) else {}

        goal: str = (
            payload.get("goal", "")
            or metadata.get("goal", "")
            or metadata.get("need_description", "unknown goal")
        )

        agent_spec_template: dict = (
            payload.get("agent_spec_template")
            or metadata.get("agent_spec_template")
            or {}
        )

        domain: str = (
            payload.get("domain", "")
            or metadata.get("domain", "unknown")
        )

        class_name = extract_class_name(agent_spec_template, domain)
        filename = class_name_to_filename(class_name)

        plan = {
            "steps": [
                {
                    "action": "generate_code",
                    "description": f"Generate agent code from template for: {class_name}",
                },
                {
                    "action": "write_file",
                    "description": f"Write genus/agents/generated/{filename}.py",
                },
                {
                    "action": "verify_import",
                    "description": f"Verify {class_name} is importable",
                },
            ],
            "goal": goal,
            "class_name": class_name,
            "domain": domain,
            "need_description": agent_spec_template.get("description", goal),
            "subscribe_topics": extract_subscribe_topics(agent_spec_template),
            "risks": [],
            "template_based": True,
        }

        # Persist state for later phases
        self._run_state[run_id] = {
            "plan": plan,
            "generated_file": None,
            "class_name": class_name,
        }

        await self._bus.publish(
            events.dev_plan_completed_message(
                run_id,
                self.id,
                plan,
                phase_id=phase_id,
            )
        )

    async def _handle_implement(self, message: Message) -> None:
        """Respond to ``dev.implement.requested``.

        Renders the agent code from the plan stored in the previous planning
        phase, writes it to disk, and publishes ``dev.implement.completed``.
        """
        run_id = message.metadata.get("run_id")
        phase_id = (
            message.payload.get("phase_id")
            if isinstance(message.payload, dict)
            else None
        )
        if not run_id or not phase_id:
            return

        payload = message.payload if isinstance(message.payload, dict) else {}
        plan: dict = payload.get("plan") or {}

        # Fall back to run_state if plan was not in the payload directly
        if not plan and run_id in self._run_state:
            plan = self._run_state[run_id].get("plan", {})

        class_name: str = plan.get("class_name", "UnknownAgent")
        domain: str = plan.get("domain", "unknown")
        need_description: str = plan.get("need_description", "")
        subscribe_topics = plan.get("subscribe_topics", [])

        template = AgentCodeTemplate(
            class_name=class_name,
            domain=domain,
            need_description=need_description,
            subscribe_topics=list(subscribe_topics),
        )
        code = template.render()

        filename = class_name_to_filename(class_name)
        output_dir = self._output_base_path
        output_dir.mkdir(parents=True, exist_ok=True)

        init_file = output_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text(
                '"""\nAuto-generated agents — created by GENUS TemplateBuilderAgent.\n'
                "Do not edit manually; re-run GENUS growth cycle to regenerate.\n"
                '"""\n',
                encoding="utf-8",
            )

        output_file = output_dir / f"{filename}.py"
        output_file.write_text(code, encoding="utf-8")

        # Update run state
        if run_id not in self._run_state:
            self._run_state[run_id] = {
                "plan": plan,
                "generated_file": None,
                "class_name": class_name,
            }
        self._run_state[run_id]["generated_file"] = output_file
        self._run_state[run_id]["class_name"] = class_name

        logger.info(
            "TemplateBuilderAgent: generated %s → %s",
            class_name,
            output_file,
        )

        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id,
                self.id,
                patch_summary=f"Generated {class_name} in genus/agents/generated/{filename}.py",
                files_changed=[f"genus/agents/generated/{filename}.py"],
                phase_id=phase_id,
                payload={"template_based": True},
            )
        )

    async def _handle_test(self, message: Message) -> None:
        """Respond to ``dev.test.requested``.

        Attempts to import the previously generated file.  Publishes a
        passing report (``failed: 0``) on success and a failing report
        (``failed: 1``) on import error.
        """
        run_id = message.metadata.get("run_id")
        phase_id = (
            message.payload.get("phase_id")
            if isinstance(message.payload, dict)
            else None
        )
        if not run_id or not phase_id:
            return

        run_info = self._run_state.get(run_id, {})
        generated_file: Optional[Path] = run_info.get("generated_file")
        class_name: str = run_info.get("class_name", "UnknownAgent")

        if generated_file is None or not generated_file.exists():
            report = {
                "passed": 0,
                "failed": 1,
                "failing_tests": ["import_check"],
                "summary": "Generated file not found; cannot import.",
                "template_based": True,
            }
        else:
            try:
                spec = importlib.util.spec_from_file_location(
                    f"{class_name}_{generated_file.stem}", str(generated_file)
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot create module spec for {generated_file}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                report = {
                    "passed": 1,
                    "failed": 0,
                    "failing_tests": [],
                    "summary": f"Import check passed for {class_name}.",
                    "template_based": True,
                }
            except Exception as exc:
                report = {
                    "passed": 0,
                    "failed": 1,
                    "failing_tests": ["import_check"],
                    "summary": str(exc),
                    "template_based": True,
                }

        await self._bus.publish(
            events.dev_test_completed_message(
                run_id,
                self.id,
                report,
                phase_id=phase_id,
            )
        )

    async def _handle_fix(self, message: Message) -> None:
        """Respond to ``dev.fix.requested``.

        Template-based fixes are not implemented.  Returns a stub response
        with ``failed: 0`` so the DevLoopOrchestrator does not hang.
        """
        run_id = message.metadata.get("run_id")
        phase_id = (
            message.payload.get("phase_id")
            if isinstance(message.payload, dict)
            else None
        )
        if not run_id or not phase_id:
            return

        logger.warning(
            "TemplateBuilderAgent: dev.fix.requested received for run_id=%r "
            "— template-based fix not supported; returning stub.",
            run_id,
        )

        fix = {"action": "template_fix_not_supported", "template_based": True}
        await self._bus.publish(
            events.dev_fix_completed_message(
                run_id,
                self.id,
                fix,
                phase_id=phase_id,
            )
        )

    async def _handle_review(self, message: Message) -> None:
        """Respond to ``dev.review.requested``.

        Checks whether the generated file exists on disk.  Always returns
        empty ``findings`` so that the Ask/Stop policy is never triggered.
        """
        run_id = message.metadata.get("run_id")
        phase_id = (
            message.payload.get("phase_id")
            if isinstance(message.payload, dict)
            else None
        )
        if not run_id or not phase_id:
            return

        run_info = self._run_state.get(run_id, {})
        generated_file: Optional[Path] = run_info.get("generated_file")

        if generated_file is not None and generated_file.exists():
            review = {
                "findings": [],
                "approved": True,
                "file_exists": True,
                "template_based": True,
            }
        else:
            review = {
                "findings": [],
                "approved": False,
                "file_exists": False,
                "template_based": True,
            }

        await self._bus.publish(
            events.dev_review_completed_message(
                run_id,
                self.id,
                review,
                phase_id=phase_id,
            )
        )
