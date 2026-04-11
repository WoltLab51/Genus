"""
Integration Tests — AgentBootstrapper Security (Phase 11c)

End-to-end test: malicious generated code is rejected before being loaded
into the main process.
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import List

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.topic_registry import TopicRegistry
from genus.growth.bootstrapper import AgentBootstrapper


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

    bus.subscribe(topic, f"__col_{topic}__", _handler)
    return collected


# ---------------------------------------------------------------------------
# Malicious code fixtures
# ---------------------------------------------------------------------------

_MALICIOUS_EVAL_CODE = textwrap.dedent(
    """\
    from genus.core.agent import Agent

    class EvilAgent(Agent):
        async def initialize(self):
            eval("__import__('os').system('rm -rf /')")
        async def start(self): pass
        async def stop(self): pass
        async def process_message(self, message): pass
    """
)

_MALICIOUS_EXEC_CODE = textwrap.dedent(
    """\
    from genus.core.agent import Agent

    class ExecAgent(Agent):
        async def initialize(self):
            exec("import os; os.getcwd()")
        async def start(self): pass
        async def stop(self): pass
        async def process_message(self, message): pass
    """
)

_MALICIOUS_SUBPROCESS_IMPORT = textwrap.dedent(
    """\
    import subprocess
    from genus.core.agent import Agent

    class SubprocAgent(Agent):
        async def initialize(self):
            subprocess.run(['ls'], capture_output=True)
        async def start(self): pass
        async def stop(self): pass
        async def process_message(self, message): pass
    """
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMaliciousCodeIsRejected:
    async def test_eval_code_is_rejected_and_not_loaded(
        self, tmp_path: Path
    ) -> None:
        """Generated code with eval() is rejected; agent.bootstrap_failed published."""
        agent_file = tmp_path / "evil_agent.py"
        agent_file.write_text(_MALICIOUS_EVAL_CODE, encoding="utf-8")

        bus = _make_bus()
        failed_events: List[Message] = _collect(bus, "agent.bootstrap_failed")
        bootstrapped_events: List[Message] = _collect(bus, "agent.bootstrapped")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            sandbox_runner=None,  # Static validation is always active
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bootstrapper.start()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={
                    "agent_name": "EvilAgent",
                    "agent_id": "evil-001",
                    "domain": "test",
                },
                sender_id="test",
            )
        )

        # Give event loop a tick to process
        await asyncio.sleep(0)

        assert len(failed_events) == 1, (
            f"Expected 1 bootstrap_failed event, got {len(failed_events)}"
        )
        assert len(bootstrapped_events) == 0, (
            "agent.bootstrapped must NOT be emitted for malicious code"
        )
        assert "evil-001" not in bootstrapper._active_agents, (
            "EvilAgent must NOT appear in _active_agents"
        )

    async def test_eval_code_error_type_is_validation_failed(
        self, tmp_path: Path
    ) -> None:
        """agent.bootstrap_failed payload has error_type='validation_failed'."""
        agent_file = tmp_path / "evil_agent.py"
        agent_file.write_text(_MALICIOUS_EVAL_CODE, encoding="utf-8")

        bus = _make_bus()
        failed_events: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()
        await bootstrapper.start()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={
                    "agent_name": "EvilAgent",
                    "agent_id": "evil-001",
                    "domain": "test",
                },
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert len(failed_events) == 1
        assert failed_events[0].payload.get("error_type") == "validation_failed"

    async def test_exec_code_is_rejected(self, tmp_path: Path) -> None:
        """Code with exec() is rejected."""
        agent_file = tmp_path / "exec_agent.py"
        agent_file.write_text(_MALICIOUS_EXEC_CODE, encoding="utf-8")

        bus = _make_bus()
        failed_events: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={
                    "agent_name": "ExecAgent",
                    "agent_id": "exec-001",
                    "domain": "test",
                },
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert len(failed_events) == 1
        assert "exec-001" not in bootstrapper._active_agents

    async def test_subprocess_import_is_rejected(self, tmp_path: Path) -> None:
        """Code that imports subprocess is rejected (not in whitelist)."""
        agent_file = tmp_path / "subproc_agent.py"
        agent_file.write_text(_MALICIOUS_SUBPROCESS_IMPORT, encoding="utf-8")

        bus = _make_bus()
        failed_events: List[Message] = _collect(bus, "agent.bootstrap_failed")

        bootstrapper = AgentBootstrapper(
            message_bus=bus,
            topic_registry=_make_registry(),
            generated_agents_path=tmp_path,
        )
        await bootstrapper.initialize()

        await bus.publish(
            Message(
                topic="dev.loop.completed",
                payload={
                    "agent_name": "SubprocAgent",
                    "agent_id": "sub-001",
                    "domain": "test",
                },
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert len(failed_events) == 1
        assert "sub-001" not in bootstrapper._active_agents

    async def test_valid_code_is_accepted(self, tmp_path: Path) -> None:
        """Valid agent code passes validation and bootstraps successfully."""
        import textwrap

        valid_code = textwrap.dedent(
            """\
            from __future__ import annotations
            from typing import Optional
            from genus.communication.message_bus import Message, MessageBus
            from genus.core.agent import Agent, AgentState

            class GoodAgent(Agent):
                def __init__(
                    self,
                    message_bus: MessageBus,
                    agent_id: Optional[str] = None,
                    name: Optional[str] = None,
                ) -> None:
                    super().__init__(agent_id=agent_id, name=name or "GoodAgent")
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
        agent_file = tmp_path / "good_agent.py"
        agent_file.write_text(valid_code, encoding="utf-8")

        bus = _make_bus()
        bootstrapped: List[Message] = _collect(bus, "agent.bootstrapped")
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
                payload={
                    "agent_name": "GoodAgent",
                    "agent_id": "good-001",
                    "domain": "test",
                },
                sender_id="test",
            )
        )
        await asyncio.sleep(0)

        assert len(failed) == 0, f"Unexpected failures: {[m.payload for m in failed]}"
        assert len(bootstrapped) == 1
        assert "GoodAgent" in bootstrapper._active_agents
