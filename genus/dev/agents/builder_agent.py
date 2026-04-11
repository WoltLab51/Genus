"""
Builder Agent

Subscribes to dev.implement.requested and publishes dev.implement.completed
or dev.implement.failed.

PR #28: Now supports real workspace operations (write files, git commit).
Phase 10c: Optional LLM-based code generation via LLMRouter.
"""

import ast
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.tools.repo_write import write_text_file
from genus.tools import git_tools

logger = logging.getLogger(__name__)

_STUB_CODE = "# stub"
_STUB_PATCH_SUMMARY = "Implemented planned changes (placeholder)"
_STUB_FILES_CHANGED = ["README.md"]


class BuilderAgent(DevAgentBase):
    """Agent that responds to implementation requests.

    Args:
        bus:                  MessageBus instance.
        agent_id:             Unique identifier for this agent.
        mode:                 Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:           If mode=="fail" and topic matches, publish failed response.
        workspace:            Optional RunWorkspace for real file operations (PR #28).
        branch_name:          Optional branch name to create before implementing.
        allowed_write_paths:  Allowlist of paths where writes are permitted.
        journal:              Optional RunJournal for logging tool usage.
        llm_router:           Optional LLMRouter. When provided (and no workspace) the
                              agent uses the LLM to generate Python code. When None,
                              stub behaviour is used (backward compatible).

    Example::

        # Placeholder mode (backward compatible)
        builder = BuilderAgent(bus, "builder-1", mode="ok")
        builder.start()

        # Real workspace mode (PR #28)
        builder = BuilderAgent(
            bus, "builder-1",
            workspace=workspace,
            branch_name="feature/test",
            allowed_write_paths=["docs/"],
        )
        builder.start()

        # LLM code-generation mode (Phase 10c)
        builder = BuilderAgent(bus, "builder-1", llm_router=router)
        builder.start()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "BuilderAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
        workspace: Optional[RunWorkspace] = None,
        branch_name: Optional[str] = None,
        allowed_write_paths: Optional[List[str]] = None,
        journal: Optional[RunJournal] = None,
        llm_router: Optional[Any] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._workspace = workspace
        self._branch_name = branch_name
        self._allowed_write_paths = allowed_write_paths or []
        self._journal = journal
        self._llm_router = llm_router

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handlers for dev.implement.requested and dev.fix.requested."""
        return [
            (topics.DEV_IMPLEMENT_REQUESTED, self._handle_implement_requested),
            (topics.DEV_FIX_REQUESTED, self._handle_fix_requested),
        ]

    async def _handle_implement_requested(self, msg: Message) -> None:
        """Handle dev.implement.requested messages."""
        # Validate metadata
        run_id = msg.metadata.get("run_id")
        if not run_id:
            return

        # Validate payload
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return

        # Get iteration from payload (optional, default 0)
        iteration = msg.payload.get("iteration", 0)

        # Check if we should simulate failure
        should_fail = (
            self._mode == "fail"
            and (self._fail_topic is None or self._fail_topic == msg.topic)
        )

        if should_fail:
            # Publish failed response
            await self._bus.publish(
                events.dev_implement_failed_message(
                    run_id,
                    self.agent_id,
                    "Implementation failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Determine implementation mode
        if self._workspace is not None:
            # Real implementation (PR #28)
            await self._implement_with_workspace(run_id, phase_id, iteration)
        elif self._llm_router is not None:
            # LLM code generation (Phase 10c)
            await self._implement_with_llm(run_id, phase_id, msg)
        else:
            # Placeholder implementation (backward compatible)
            await self._implement_placeholder(run_id, phase_id)

    async def _implement_placeholder(self, run_id: str, phase_id: str) -> None:
        """Placeholder implementation (backward compatible).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
        """
        # Build placeholder implementation result
        patch_summary = _STUB_PATCH_SUMMARY
        files_changed = list(_STUB_FILES_CHANGED)

        # Publish completed response
        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id,
                self.agent_id,
                patch_summary,
                files_changed,
                phase_id=phase_id,
            )
        )

    async def _implement_with_llm(
        self, run_id: str, phase_id: str, msg: Message
    ) -> None:
        """LLM-based code generation (Phase 10c).

        Args:
            run_id:   The run identifier.
            phase_id: The phase identifier for correlation.
            msg:      The original dev.implement.requested message.
        """
        payload = msg.payload if isinstance(msg.payload, dict) else {}
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}

        plan: Dict[str, Any] = payload.get("plan") or {}
        plan_steps: List[str] = plan.get("steps", [])
        agent_spec_template: Optional[Dict[str, Any]] = (
            payload.get("agent_spec_template") or metadata.get("agent_spec_template")
        )
        domain: Optional[str] = payload.get("domain") or metadata.get("domain")

        llm_result = await self._generate_code_with_llm(
            plan_steps, agent_spec_template, domain
        )

        if llm_result is not None:
            code = llm_result.get("code", _STUB_CODE)
            filename = llm_result.get("filename", "generated_agent.py")
            language = llm_result.get("language", "python")
        else:
            code = _STUB_CODE
            filename = "generated_agent.py"
            language = "python"

        patch_summary = f"Generated {filename} ({language})"
        await self._bus.publish(
            events.dev_implement_completed_message(
                run_id,
                self.agent_id,
                patch_summary,
                [filename],
                phase_id=phase_id,
                payload={"code": code, "filename": filename, "language": language},
            )
        )

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def _generate_code_with_llm(
        self,
        plan_steps: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
        domain: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Call the LLM router and return parsed code data, or None on error."""
        from genus.llm.exceptions import LLMProviderUnavailableError, LLMResponseParseError
        from genus.llm.router import TaskType

        agent_name = "GeneratedAgent"
        if agent_spec_template:
            agent_name = agent_spec_template.get("name", agent_name)

        try:
            messages = self._build_code_prompt(plan_steps, agent_spec_template, domain)
            response = await self._llm_router.complete(
                messages, task_type=TaskType.CODE_GEN
            )
            return self._parse_code_response(response.content, agent_name)
        except LLMResponseParseError as exc:
            logger.warning("BuilderAgent: LLM response parse error, using fallback: %s", exc)
            return None
        except LLMProviderUnavailableError as exc:
            logger.warning("BuilderAgent: LLM provider unavailable, using stub: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("BuilderAgent: unexpected LLM error, using stub: %s", exc)
            return None

    def _build_code_prompt(
        self,
        plan_steps: List[str],
        agent_spec_template: Optional[Dict[str, Any]],
        domain: Optional[str],
    ) -> List[Any]:
        """Build the list of LLMMessages for the code-generation prompt."""
        from genus.llm.models import LLMMessage, LLMRole

        system = (
            "Du bist ein erfahrener Python-Entwickler im GENUS-System.\n"
            "Deine Aufgabe: Implementiere einen GENUS-Agenten basierend auf dem Plan.\n\n"
            "Ein GENUS-Agent hat immer diese Struktur:\n"
            "from __future__ import annotations\n"
            "from typing import Optional\n"
            "from genus.communication.message_bus import Message, MessageBus\n"
            "from genus.core.agent import Agent, AgentState\n\n"
            "class MyAgent(Agent):\n"
            "    def __init__(self, message_bus: MessageBus, agent_id: Optional[str] = None,"
            " name: Optional[str] = None) -> None:\n"
            "        super().__init__(agent_id=agent_id, name=name or 'MyAgent')\n"
            "        self._bus = message_bus\n\n"
            "    async def initialize(self) -> None:\n"
            "        self._bus.subscribe('my.topic', self.id, self.process_message)\n"
            "        self._transition_state(AgentState.INITIALIZED)\n\n"
            "    async def start(self) -> None:\n"
            "        self._transition_state(AgentState.RUNNING)\n\n"
            "    async def stop(self) -> None:\n"
            "        self._bus.unsubscribe_all(self.id)\n"
            "        self._transition_state(AgentState.STOPPED)\n\n"
            "    async def process_message(self, message: Message) -> None:\n"
            "        pass\n\n"
            "Antworte AUSSCHLIESSLICH mit dem Python-Code, ohne Markdown-Codeblöcke,"
            " ohne Erklärungen."
        )

        user_parts = []
        if agent_spec_template:
            name = agent_spec_template.get("name", "GeneratedAgent")
            desc = agent_spec_template.get("description", "")
            spec_topics = agent_spec_template.get("topics", [])
            user_parts.append(f"Agent-Name: {name}")
            if desc:
                user_parts.append(f"Beschreibung: {desc}")
            if spec_topics:
                user_parts.append(f"Subscribe auf Topics: {', '.join(spec_topics)}")

        if plan_steps:
            user_parts.append(
                "Implementierungsplan:\n"
                + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan_steps))
            )

        return [
            LLMMessage(role=LLMRole.SYSTEM, content=system),
            LLMMessage(role=LLMRole.USER, content="\n\n".join(user_parts)),
        ]

    def _parse_code_response(self, content: str, agent_name: str) -> Dict[str, Any]:
        """Extract Python code from the LLM response.

        Strips markdown fences if present and validates syntax via ast.parse().

        Raises:
            LLMResponseParseError: when the generated code has a syntax error.
        """
        from genus.dev.agents.agent_code_template import class_name_to_filename
        from genus.llm.exceptions import LLMResponseParseError

        code = content.strip()
        if code.startswith("```"):
            code = re.sub(r"^```(?:python)?\n?", "", code)
            code = re.sub(r"\n?```$", "", code)
        code = code.strip()

        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise LLMResponseParseError(
                f"BuilderAgent: generated code has syntax error: {exc}"
            ) from exc

        filename = class_name_to_filename(agent_name) + ".py"
        return {"code": code, "filename": filename, "language": "python"}

    async def _implement_with_workspace(self, run_id: str, phase_id: str, iteration: int = 0) -> None:
        """Real implementation using workspace (PR #28).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
            iteration: The current iteration number (default 0).
        """
        try:
            files_changed = []

            # Step 1: Create branch if requested
            if self._branch_name:
                if self._journal:
                    self._journal.log_tool_use(
                        phase="implement",
                        tool_name="git_create_branch",
                        phase_id=phase_id,
                        branch_name=self._branch_name,
                    )

                result = await git_tools.git_create_branch(
                    self._workspace, self._branch_name
                )

                if not result.success:
                    await self._bus.publish(
                        events.dev_implement_failed_message(
                            run_id,
                            self.agent_id,
                            "Failed to create branch: {}".format(result.error),
                            phase_id=phase_id,
                        )
                    )
                    return

            # Step 2: Write a simple file change
            # For v1, we write a note to docs/DEVLOOP_NOTE.md
            content = "# DevLoop Note\n\nThis file was created by BuilderAgent during implementation.\n\nRun ID: {}\n".format(
                run_id
            )

            if self._journal:
                self._journal.log_tool_use(
                    phase="implement",
                    tool_name="write_text_file",
                    phase_id=phase_id,
                    rel_path="docs/DEVLOOP_NOTE.md",
                )

            write_result = write_text_file(
                repo_root=self._workspace.repo_dir,
                rel_path="docs/DEVLOOP_NOTE.md",
                content=content,
                allowed_paths=self._allowed_write_paths,
            )

            if not write_result.success:
                await self._bus.publish(
                    events.dev_implement_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to write file: {}".format(write_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            files_changed.append("docs/DEVLOOP_NOTE.md")

            # Step 3: Stage changes
            if self._journal:
                self._journal.log_tool_use(
                    phase="implement",
                    tool_name="git_add_all",
                    phase_id=phase_id,
                )

            add_result = await git_tools.git_add_all(self._workspace)

            if not add_result.success:
                await self._bus.publish(
                    events.dev_implement_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to stage changes: {}".format(add_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            # Step 4: Commit changes
            commit_message = "feat: GENUS implement (iter {})\n\nImplemented planned changes\nGenerated by GENUS BuilderAgent\nRun ID: {}".format(
                iteration, run_id
            )

            if self._journal:
                self._journal.log_tool_use(
                    phase="implement",
                    tool_name="git_commit",
                    phase_id=phase_id,
                    message=commit_message,
                )

            commit_result = await git_tools.git_commit(self._workspace, commit_message)

            if not commit_result.success:
                await self._bus.publish(
                    events.dev_implement_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to commit: {}".format(commit_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            # Step 5: Get final status/diff to report files changed
            status_result = await git_tools.git_status(self._workspace)
            patch_summary = "Created/updated {} file(s)".format(len(files_changed))

            if commit_result.data.get("nothing_to_commit"):
                patch_summary = "No changes to commit (working tree clean)"

            # Publish completed response
            await self._bus.publish(
                events.dev_implement_completed_message(
                    run_id,
                    self.agent_id,
                    patch_summary,
                    files_changed,
                    phase_id=phase_id,
                )
            )

        except Exception as e:
            # Catch any unexpected errors
            await self._bus.publish(
                events.dev_implement_failed_message(
                    run_id,
                    self.agent_id,
                    "Unexpected error: {}".format(str(e)),
                    phase_id=phase_id,
                )
            )

    async def _handle_fix_requested(self, msg: Message) -> None:
        """Handle dev.fix.requested messages."""
        # Validate metadata
        run_id = msg.metadata.get("run_id")
        if not run_id:
            return

        # Validate payload
        phase_id = msg.payload.get("phase_id")
        if not phase_id:
            return

        # Get iteration from payload (optional)
        iteration = msg.payload.get("iteration", 0)

        # Check if we should simulate failure
        should_fail = (
            self._mode == "fail"
            and (self._fail_topic is None or self._fail_topic == msg.topic)
        )

        if should_fail:
            # Publish failed response
            await self._bus.publish(
                events.dev_fix_failed_message(
                    run_id,
                    self.agent_id,
                    "Fix failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Determine if we're in workspace mode or placeholder mode
        if self._workspace is not None:
            # Real fix implementation (PR #30)
            await self._fix_with_workspace(run_id, phase_id, iteration, msg.payload.get("findings", []))
        else:
            # Placeholder fix implementation (backward compatible)
            await self._fix_placeholder(run_id, phase_id)

    async def _fix_placeholder(self, run_id: str, phase_id: str) -> None:
        """Placeholder fix implementation (backward compatible).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
        """
        # Build placeholder fix result
        fix_artifact = {
            "patch_summary": "Applied fixes (placeholder)",
            "files_changed": ["README.md"],
            "fixes_applied": ["placeholder fix"],
        }

        # Publish completed response
        await self._bus.publish(
            events.dev_fix_completed_message(
                run_id,
                self.agent_id,
                fix_artifact,
                phase_id=phase_id,
            )
        )

    async def _fix_with_workspace(
        self, run_id: str, phase_id: str, iteration: int, findings: List
    ) -> None:
        """Real fix implementation using workspace.

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
            iteration: The current iteration number.
            findings: List of findings/failures to fix.
        """
        try:
            files_changed = []

            # For v1, we write a fix note to docs/DEVLOOP_FIX_NOTE.md
            # In a real implementation, this would analyze findings and apply appropriate fixes
            content = "# DevLoop Fix Note\n\nThis file was created by BuilderAgent during fix phase.\n\nRun ID: {}\nIteration: {}\n\n## Findings\n".format(
                run_id, iteration
            )

            for idx, finding in enumerate(findings):
                content += "\n### Finding {}\n".format(idx + 1)
                content += "- Type: {}\n".format(finding.get("type", "unknown"))
                content += "- Message: {}\n".format(finding.get("message", "no message"))

            if self._journal:
                self._journal.log_tool_use(
                    phase="fix",
                    tool_name="write_text_file",
                    phase_id=phase_id,
                    rel_path="docs/DEVLOOP_FIX_NOTE.md",
                    iteration=iteration,
                )

            write_result = write_text_file(
                repo_root=self._workspace.repo_dir,
                rel_path="docs/DEVLOOP_FIX_NOTE.md",
                content=content,
                allowed_paths=self._allowed_write_paths,
            )

            if not write_result.success:
                await self._bus.publish(
                    events.dev_fix_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to write file: {}".format(write_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            files_changed.append("docs/DEVLOOP_FIX_NOTE.md")

            # Stage changes
            if self._journal:
                self._journal.log_tool_use(
                    phase="fix",
                    tool_name="git_add_all",
                    phase_id=phase_id,
                    iteration=iteration,
                )

            add_result = await git_tools.git_add_all(self._workspace)

            if not add_result.success:
                await self._bus.publish(
                    events.dev_fix_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to stage changes: {}".format(add_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            # Commit changes with iteration info
            commit_message = "fix: GENUS fix (iter {})\n\nApplied fixes for test failures\nGenerated by GENUS BuilderAgent\nRun ID: {}".format(
                iteration, run_id
            )

            if self._journal:
                self._journal.log_tool_use(
                    phase="fix",
                    tool_name="git_commit",
                    phase_id=phase_id,
                    message=commit_message,
                    iteration=iteration,
                )

            commit_result = await git_tools.git_commit(self._workspace, commit_message)

            if not commit_result.success:
                await self._bus.publish(
                    events.dev_fix_failed_message(
                        run_id,
                        self.agent_id,
                        "Failed to commit: {}".format(commit_result.error),
                        phase_id=phase_id,
                    )
                )
                return

            # Build fix artifact
            patch_summary = "Applied {} fix(es) in iteration {}".format(
                len(findings), iteration
            )

            if commit_result.data.get("nothing_to_commit"):
                patch_summary = "No changes to commit (working tree clean)"

            fix_artifact = {
                "patch_summary": patch_summary,
                "files_changed": files_changed,
                "fixes_applied": [f.get("message", "unknown") for f in findings],
                "iteration": iteration,
            }

            # Publish completed response
            await self._bus.publish(
                events.dev_fix_completed_message(
                    run_id,
                    self.agent_id,
                    fix_artifact,
                    phase_id=phase_id,
                )
            )

        except Exception as e:
            # Catch any unexpected errors
            await self._bus.publish(
                events.dev_fix_failed_message(
                    run_id,
                    self.agent_id,
                    "Unexpected error: {}".format(str(e)),
                    phase_id=phase_id,
                )
            )
