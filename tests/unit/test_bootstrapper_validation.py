"""
Unit Tests — AgentBootstrapper Phase 11c (Code Validation)

Verifies:
- Valid code → _load_agent_from_file() succeeds
- Code with eval() → AgentValidationError + agent.bootstrap_failed published
- CodeValidator is always called (even without SandboxRunner)
- With SandboxRunner=None → no sandbox run, but static validation still runs
- SECURITY-TODO is no longer in bootstrapper source
- AgentValidationError payload has error_type="validation_failed"
- topic_registry is optional (backwards-compat with existing tests)
"""

from __future__ import annotations

import inspect
import textwrap
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicRegistry
from genus.growth.bootstrapper import AgentBootstrapper, AgentValidationError
from genus.growth.code_validator import CodeValidator, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bus() -> MessageBus:
    return MessageBus()


def _make_registry() -> TopicRegistry:
    return TopicRegistry()


def _collect(bus: MessageBus, topic: str) -> List[Message]:
    collected: List[Message] = []

    async def _handler(msg: Message) -> None:
        collected.append(msg)

    bus.subscribe(topic, f"__collector_{topic}__", _handler)
    return collected


def _payload(
    agent_name: str = "DemoAgent",
    agent_id: str = "demo-001",
    domain: str = "test",
) -> dict:
    return {"agent_name": agent_name, "agent_id": agent_id, "domain": domain}


def _write_valid_agent(path: Path, class_name: str) -> None:
    """Write minimal valid agent code."""
    code = textwrap.dedent(
        f"""\
        from __future__ import annotations
        from typing import Optional
        from genus.communication.message_bus import Message, MessageBus
        from genus.core.agent import Agent, AgentState

        class {class_name}(Agent):
            def __init__(
                self,
                message_bus: MessageBus,
                agent_id: Optional[str] = None,
                name: Optional[str] = None,
            ) -> None:
                super().__init__(agent_id=agent_id, name=name or "{class_name}")
                self._bus = message_bus

            async def initialize(self) -> None:
                self._transition_state(AgentState.INITIALIZED)

            async def start(self) -> None:
                self._transition_state(AgentState.RUNNING)

            async def stop(self) -> None:
                self._bus.unsubscribe_all(self.id)
                self._transition_state(AgentState.STOPPED)

            async def process_message(self, message: Message) -> None:
                pass
        """
    )
    path.write_text(code, encoding="utf-8")


def _write_eval_agent(path: Path, class_name: str) -> None:
    """Write agent code containing eval() (should be rejected)."""
    code = textwrap.dedent(
        f"""\
        from genus.core.agent import Agent

        class {class_name}(Agent):
            async def initialize(self):
                eval("1 + 1")
            async def start(self): pass
            async def stop(self): pass
            async def process_message(self, message): pass
        """
    )
    path.write_text(code, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests — SECURITY-TODO removed
# ---------------------------------------------------------------------------

class TestSecurityTodoRemoved:
    def test_security_todo_not_in_bootstrapper_source(self) -> None:
        """The SECURITY-TODO comment must be gone from bootstrapper.py."""
        import genus.growth.bootstrapper as mod

        source_file = Path(mod.__file__)
        content = source_file.read_text(encoding="utf-8")
        assert "SECURITY-TODO" not in content, (
            "SECURITY-TODO comment still present in bootstrapper.py"
        )


# ---------------------------------------------------------------------------
# Tests — CodeValidator always active
# ---------------------------------------------------------------------------

class TestCodeValidatorAlwaysActive:
    async def test_code_validator_called_without_sandbox_runner(
        self, tmp_path: Path
    ) -> None:
        """CodeValidator is invoked even when sandbox_runner=None."""
        calls: List[str] = []

        class _TrackingValidator(CodeValidator):
            def validate(self, code, filename="<generated>"):
                calls.append(filename)
                return super().validate(code, filename=filename)

        agent_file = tmp_path / "demo_agent.py"
        _write_valid_agent(agent_file, "DemoAgent")

        bus = _make_bus()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            sandbox_runner=None,
            code_validator=_TrackingValidator(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="DemoAgent"),
                sender_id="test",
            )
        )

        assert len(calls) == 1, "CodeValidator.validate() must be called once"
        assert "demo_agent.py" in calls[0]

    async def test_no_sandbox_run_without_sandbox_runner(
        self, tmp_path: Path
    ) -> None:
        """With sandbox_runner=None, _run_sandbox_check is never awaited."""
        agent_file = tmp_path / "demo_agent.py"
        _write_valid_agent(agent_file, "DemoAgent")

        bus = _make_bus()
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            sandbox_runner=None,  # explicit None → no sandbox
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="DemoAgent"),
                sender_id="test",
            )
        )

        # Bootstrap should succeed without sandbox
        assert len(bootstrapped) == 1


# ---------------------------------------------------------------------------
# Tests — AgentValidationError on bad code
# ---------------------------------------------------------------------------

class TestAgentValidationError:
    async def test_eval_in_code_raises_validation_error_event(
        self, tmp_path: Path
    ) -> None:
        """Code with eval() → agent.bootstrap_failed published."""
        evil_file = tmp_path / "evil_agent.py"
        _write_eval_agent(evil_file, "EvilAgent")

        bus = _make_bus()
        failed: List[Message] = _collect(bus, "agent.bootstrap_failed")
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            sandbox_runner=None,
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="EvilAgent", agent_id="evil-001"),
                sender_id="test",
            )
        )

        assert len(failed) == 1, "Expected agent.bootstrap_failed event"
        assert len(bootstrapped) == 0, "agent.bootstrapped must NOT be published"

    async def test_validation_failed_payload_has_error_type(
        self, tmp_path: Path
    ) -> None:
        """agent.bootstrap_failed payload has error_type='validation_failed'."""
        evil_file = tmp_path / "evil_agent.py"
        _write_eval_agent(evil_file, "EvilAgent")

        bus = _make_bus()
        failed: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="EvilAgent", agent_id="evil-001"),
                sender_id="test",
            )
        )

        assert len(failed) == 1
        payload = failed[0].payload
        assert payload.get("error_type") == "validation_failed"

    async def test_validation_failed_payload_has_agent_name(
        self, tmp_path: Path
    ) -> None:
        """agent.bootstrap_failed payload includes agent_name."""
        evil_file = tmp_path / "evil_agent.py"
        _write_eval_agent(evil_file, "EvilAgent")

        bus = _make_bus()
        failed: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="EvilAgent", agent_id="evil-001"),
                sender_id="test",
            )
        )

        assert failed[0].payload["agent_name"] == "EvilAgent"

    async def test_evil_agent_not_in_active_agents(
        self, tmp_path: Path
    ) -> None:
        """When validation fails, agent is NOT added to _active_agents."""
        evil_file = tmp_path / "evil_agent.py"
        _write_eval_agent(evil_file, "EvilAgent")

        bus = _make_bus()
        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="EvilAgent", agent_id="evil-001"),
                sender_id="test",
            )
        )

        assert "EvilAgent" not in bootstrapper._active_agents

    async def test_validation_error_reason_contains_eval(
        self, tmp_path: Path
    ) -> None:
        """Failure reason string references the banned call."""
        evil_file = tmp_path / "evil_agent.py"
        _write_eval_agent(evil_file, "EvilAgent")

        bus = _make_bus()
        failed: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="EvilAgent"),
                sender_id="test",
            )
        )

        reason = failed[0].payload.get("reason", "")
        assert "eval" in reason.lower() or "Banned call" in reason


# ---------------------------------------------------------------------------
# Tests — optional topic_registry
# ---------------------------------------------------------------------------

class TestTopicRegistryOptional:
    async def test_bootstrapper_works_without_topic_registry(
        self, tmp_path: Path
    ) -> None:
        """AgentBootstrapper can be instantiated without topic_registry."""
        agent_file = tmp_path / "demo_agent.py"
        _write_valid_agent(agent_file, "DemoAgent")

        bus = _make_bus()
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            # No topic_registry passed
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload=_payload(agent_name="DemoAgent"),
                sender_id="test",
            )
        )

        assert len(bootstrapped) == 1


# ---------------------------------------------------------------------------
# Tests — AgentValidationError exception
# ---------------------------------------------------------------------------

class TestAgentValidationErrorException:
    def test_agent_validation_error_is_exception(self) -> None:
        """AgentValidationError inherits from Exception."""
        err = AgentValidationError("test message")
        assert isinstance(err, Exception)
        assert str(err) == "test message"

    def test_agent_validation_error_importable(self) -> None:
        """AgentValidationError can be imported from bootstrapper."""
        from genus.growth.bootstrapper import AgentValidationError as AVE

        assert AVE is AgentValidationError
