"""
Builder Agent

Subscribes to dev.implement.requested and publishes dev.implement.completed
or dev.implement.failed.

PR #28: Now supports real workspace operations (write files, git commit).
"""

from typing import Awaitable, Callable, List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.tools.repo_write import write_text_file
from genus.tools import git_tools


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
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._workspace = workspace
        self._branch_name = branch_name
        self._allowed_write_paths = allowed_write_paths or []
        self._journal = journal

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.implement.requested."""
        return [(topics.DEV_IMPLEMENT_REQUESTED, self._handle_implement_requested)]

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

        # Determine if we're in workspace mode or placeholder mode
        if self._workspace is not None:
            # Real implementation (PR #28)
            await self._implement_with_workspace(run_id, phase_id)
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
        patch_summary = "Implemented planned changes (placeholder)"
        files_changed = ["README.md"]

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

    async def _implement_with_workspace(self, run_id: str, phase_id: str) -> None:
        """Real implementation using workspace (PR #28).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
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
            commit_message = "feat: implement changes from plan\n\nGenerated by GENUS BuilderAgent\nRun ID: {}".format(
                run_id
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
