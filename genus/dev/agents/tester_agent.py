"""
Tester Agent

Subscribes to dev.test.requested and publishes dev.test.completed or
dev.test.failed.

PR #28: Now supports real test execution via SandboxRunner.
Phase B: Parses pytest output for structured results (passed, failed, errors,
         failures details, duration, status).
"""

import re
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Tuple
from genus.communication.message_bus import Message, MessageBus
from genus.dev import events, topics
from genus.dev.agents.base import DevAgentBase
from genus.workspace.workspace import RunWorkspace
from genus.memory.run_journal import RunJournal
from genus.tools.sandbox_run import sandbox_run


class TesterAgent(DevAgentBase):
    """Agent that responds to test requests.

    Args:
        bus:         MessageBus instance.
        agent_id:    Unique identifier for this agent.
        mode:        Behavior mode: "ok" (normal) or "fail" (simulate failure).
        fail_topic:  If mode=="fail" and topic matches, publish failed response.
        workspace:   Optional RunWorkspace for real test execution (PR #28).
        test_argv:   Command to run tests (default: ["python", "-m", "pytest", "-q"]).
        journal:     Optional RunJournal for logging tool usage.

    Example::

        # Placeholder mode (backward compatible)
        tester = TesterAgent(bus, "tester-1", mode="ok")
        tester.start()

        # Real sandbox mode (PR #28)
        tester = TesterAgent(
            bus, "tester-1",
            workspace=workspace,
            test_argv=["python", "-m", "pytest", "-q"],
        )
        tester.start()
    """

    def __init__(
        self,
        bus: MessageBus,
        agent_id: str = "TesterAgent",
        mode: Literal["ok", "fail"] = "ok",
        fail_topic: Optional[str] = None,
        workspace: Optional[RunWorkspace] = None,
        test_argv: Optional[List[str]] = None,
        journal: Optional[RunJournal] = None,
    ) -> None:
        super().__init__(bus, agent_id)
        self._mode = mode
        self._fail_topic = fail_topic
        self._workspace = workspace
        self._test_argv = test_argv or ["python", "-m", "pytest", "-q"]
        self._journal = journal

    def _subscribe_topics(self) -> List[Tuple[str, Callable[[Message], Awaitable[None]]]]:
        """Register handler for dev.test.requested."""
        return [(topics.DEV_TEST_REQUESTED, self._handle_test_requested)]

    async def _handle_test_requested(self, msg: Message) -> None:
        """Handle dev.test.requested messages."""
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
                events.dev_test_failed_message(
                    run_id,
                    self.agent_id,
                    "Testing failed (simulated)",
                    phase_id=phase_id,
                )
            )
            return

        # Determine if we're in workspace mode or placeholder mode
        if self._workspace is not None:
            # Real test execution (PR #28)
            await self._run_tests_in_sandbox(run_id, phase_id)
        else:
            # Placeholder test report (backward compatible)
            await self._run_tests_placeholder(run_id, phase_id)

    async def _run_tests_placeholder(self, run_id: str, phase_id: str) -> None:
        """Placeholder test execution (backward compatible).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
        """
        # Build placeholder test report
        report = {
            "passed": 42,
            "failed": 0,
            "duration_s": 3.14,
            "summary": "All tests passed (placeholder)",
            "failing_tests": [],
        }

        # Publish completed response
        await self._bus.publish(
            events.dev_test_completed_message(
                run_id,
                self.agent_id,
                report,
                phase_id=phase_id,
            )
        )

    async def _run_tests_in_sandbox(self, run_id: str, phase_id: str) -> None:
        """Real test execution via SandboxRunner (PR #28).

        Args:
            run_id: The run identifier.
            phase_id: The phase identifier for correlation.
        """
        try:
            # Log tool usage
            if self._journal:
                self._journal.log_tool_use(
                    phase="test",
                    tool_name="sandbox_run",
                    phase_id=phase_id,
                    argv=self._test_argv,
                )

            # Run tests via sandbox
            result = await sandbox_run(
                workspace=self._workspace,
                argv=self._test_argv,
                cwd=".",
                timeout_s=120.0,
            )

            # Parse pytest output for structured results (Phase B)
            combined_output = (result.stdout or "") + (result.stderr or "")
            parsed = self._parse_pytest_output(combined_output, result.exit_code)

            # Build report merging raw sandbox result with parsed pytest output
            report: Dict[str, object] = {
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "duration_s": parsed["duration_s"] if parsed["duration_s"] else result.duration_s,
                "stdout_summary": result.stdout[:500] if result.stdout else "",
                "stderr_summary": result.stderr[:500] if result.stderr else "",
                "summary": self._generate_test_summary(result),
                # Structured pytest results (Phase B)
                "passed": parsed["passed"],
                "failed": parsed["failed"],
                "errors": parsed["errors"],
                "status": parsed["status"],
                "failures": parsed["failures"],
                # failing_tests for backward compatibility with TestPhaseRunner / FixPhaseRunner
                "failing_tests": [f["test"] for f in parsed["failures"]],
            }

            # Decide if test passed or failed based on exit code
            if result.exit_code == 0 and not result.timed_out:
                # Tests passed
                await self._bus.publish(
                    events.dev_test_completed_message(
                        run_id,
                        self.agent_id,
                        report,
                        phase_id=phase_id,
                    )
                )
            else:
                # Tests failed or timed out
                error_msg = "Tests failed with exit code {}".format(result.exit_code)
                if result.timed_out:
                    error_msg = "Tests timed out after {:.1f}s".format(result.duration_s)

                await self._bus.publish(
                    events.dev_test_failed_message(
                        run_id,
                        self.agent_id,
                        error_msg,
                        phase_id=phase_id,
                    )
                )

        except Exception as e:
            # Catch any unexpected errors
            await self._bus.publish(
                events.dev_test_failed_message(
                    run_id,
                    self.agent_id,
                    "Unexpected error running tests: {}".format(str(e)),
                    phase_id=phase_id,
                )
            )

    def _parse_pytest_output(self, output: str, returncode: int) -> Dict[str, object]:
        """Parse pytest output into a structured result dict.

        Parses lines such as::

            PASSED tests/test_foo.py::test_bar
            FAILED tests/test_foo.py::test_baz - AssertionError: expected 1, got 2
            2 passed, 1 failed in 0.38s

        Args:
            output:     Combined stdout+stderr from the pytest run.
            returncode: Process exit code (0 = all passed, 1 = failures,
                        5 = no tests collected).

        Returns:
            Dict with keys: passed, failed, errors, status, output,
            failures (list of {test, message}), duration_s.
        """
        passed = 0
        failed = 0
        errors = 0
        failures: List[Dict[str, str]] = []
        duration_s = 0.0

        # Parse counts from summary line, e.g. "2 passed, 1 failed, 1 error in 0.42s"
        for match in re.finditer(r"(\d+) (passed|failed|error)", output):
            count = int(match.group(1))
            kind = match.group(2)
            if kind == "passed":
                passed = count
            elif kind == "failed":
                failed = count
            elif kind == "error":
                errors = count

        # Parse duration, e.g. "in 0.42s"
        duration_match = re.search(r"in ([\d.]+)s", output)
        if duration_match:
            try:
                duration_s = float(duration_match.group(1))
            except ValueError:
                pass

        # Parse "FAILED test_name - message" lines for failure details
        for line in output.splitlines():
            if line.startswith("FAILED "):
                rest = line[7:]
                if " - " in rest:
                    test_name = rest.split(" - ")[0].strip()
                    message = rest.split(" - ", 1)[1].strip()
                else:
                    test_name = rest.strip()
                    message = ""
                failures.append({"test": test_name, "message": message})

        # Determine status
        if returncode == 5:
            # pytest exit code 5 means no tests were collected
            status = "no_tests"
        elif returncode == 0:
            status = "passed"
        elif errors > 0:
            status = "error"
        else:
            status = "failed"

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "status": status,
            "output": output,
            "failures": failures,
            "duration_s": duration_s,
        }

    def _generate_test_summary(self, result) -> str:
        """Generate a human-readable test summary from sandbox result.

        Args:
            result: SandboxResult from test execution.

        Returns:
            Summary string describing test outcome.
        """
        if result.timed_out:
            return "Tests timed out after {:.1f}s".format(result.duration_s)

        if result.exit_code == 0:
            return "Tests passed (exit code 0)"

        # Try to extract pytest output
        if "passed" in result.stdout or "failed" in result.stdout:
            # Look for pytest summary line
            lines = result.stdout.split("\n")
            for line in lines:
                if "passed" in line or "failed" in line:
                    return line.strip()

        return "Tests failed with exit code {}".format(result.exit_code)
