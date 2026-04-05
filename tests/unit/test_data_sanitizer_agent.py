"""
Unit tests for DataSanitizerAgent

Covers:
- Publishes ``data.sanitized`` for every ``data.collected`` message
- Output payload has ``source``, ``data``, ``evidence`` keys
- source resolved from payload["source"]
- source resolved from metadata["source"] when not in payload
- source defaults to "unknown" when absent
- unknown source with empty/non-dict data → blocked_by_policy True
- run_id is propagated to output metadata
- missing run_id → published under "unknown", run_id_missing=True in evidence + metadata
- agent lifecycle: initialize / start / stop
- data.sanitized not published after stop
- custom policy is applied
"""

import pytest

from genus.agents.data_sanitizer_agent import (
    INPUT_TOPIC,
    OUTPUT_TOPIC,
    DataSanitizerAgent,
)
from genus.communication.message_bus import Message, MessageBus
from genus.safety.sanitization_policy import SanitizationPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "2026-04-05T14-07-12Z__sanitizer-test__abc123"


def _make_collected(
    payload: dict | None = None,
    run_id: str | None = RUN_ID,
    metadata: dict | None = None,
    sender_id: str = "collector",
) -> Message:
    meta: dict = {}
    if run_id is not None:
        meta["run_id"] = run_id
    if metadata:
        meta.update(metadata)
    return Message(
        topic=INPUT_TOPIC,
        payload=payload if payload is not None else {},
        sender_id=sender_id,
        metadata=meta,
    )


async def _setup(
    policy: SanitizationPolicy | None = None,
) -> tuple[DataSanitizerAgent, MessageBus]:
    bus = MessageBus()
    agent = DataSanitizerAgent(message_bus=bus, policy=policy)
    await agent.initialize()
    await agent.start()
    return agent, bus


# ---------------------------------------------------------------------------
# Publishes data.sanitized
# ---------------------------------------------------------------------------

class TestPublishesSanitized:
    @pytest.mark.asyncio
    async def test_publishes_data_sanitized_topic(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "test-listener", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "home-assistant"}))
        assert len(received) == 1
        assert received[0].topic == OUTPUT_TOPIC

    @pytest.mark.asyncio
    async def test_output_payload_has_required_keys(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "test-listener", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "sensor"}))
        p = received[0].payload
        assert "source" in p
        assert "data" in p
        assert "evidence" in p

    @pytest.mark.asyncio
    async def test_data_field_is_dict(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "test-listener", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "s", "metrics": {"temp": 20}}))
        assert isinstance(received[0].payload["data"], dict)

    @pytest.mark.asyncio
    async def test_evidence_field_is_dict(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "test-listener", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "s"}))
        assert isinstance(received[0].payload["evidence"], dict)


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

class TestSourceResolution:
    @pytest.mark.asyncio
    async def test_source_from_payload(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "home-assistant"}))
        assert received[0].payload["source"] == "home-assistant"

    @pytest.mark.asyncio
    async def test_source_from_metadata_when_not_in_payload(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        msg = _make_collected(payload={"metrics": {"v": 1}}, metadata={"source": "meta-source"})
        await bus.publish(msg)
        assert received[0].payload["source"] == "meta-source"

    @pytest.mark.asyncio
    async def test_source_defaults_to_unknown(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected({"metrics": {"v": 1}}))
        assert received[0].payload["source"] == "unknown"


# ---------------------------------------------------------------------------
# Unknown source / blocked_by_policy
# ---------------------------------------------------------------------------

class TestUnknownSourceBlocked:
    @pytest.mark.asyncio
    async def test_unknown_source_still_publishes(self):
        """Even when all data is removed, data.sanitized must be published."""
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        # Payload with no allowed keys, no source
        await bus.publish(_make_collected({"secret": "drop-me", "token": "abc"}))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_non_dict_payload_blocked_by_policy(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        msg = Message(
            topic=INPUT_TOPIC,
            payload="raw string payload",
            sender_id="collector",
            metadata={"run_id": RUN_ID},
        )
        await bus.publish(msg)
        assert len(received) == 1
        ev = received[0].payload["evidence"]
        assert ev["blocked_by_policy"] is True

    @pytest.mark.asyncio
    async def test_no_allowed_keys_yields_blocked_by_policy(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected({"raw": "x", "token": "y"}))
        ev = received[0].payload["evidence"]
        assert ev["blocked_by_policy"] is True

    @pytest.mark.asyncio
    async def test_unknown_source_with_no_data_is_blocked(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected({}))
        p = received[0].payload
        assert p["source"] == "unknown"
        # empty input → no fields removed → blocked_by_policy False
        assert p["evidence"]["blocked_by_policy"] is False
        assert p["data"] == {}


# ---------------------------------------------------------------------------
# run_id propagation
# ---------------------------------------------------------------------------

class TestRunIdPropagation:
    @pytest.mark.asyncio
    async def test_run_id_propagated_to_output_metadata(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected(run_id=RUN_ID))
        assert received[0].metadata.get("run_id") == RUN_ID

    @pytest.mark.asyncio
    async def test_missing_run_id_published_under_unknown(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected(run_id=None))
        assert received[0].metadata.get("run_id") == "unknown"

    @pytest.mark.asyncio
    async def test_missing_run_id_sets_run_id_missing_in_metadata(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected(run_id=None))
        assert received[0].metadata.get("run_id_missing") is True

    @pytest.mark.asyncio
    async def test_missing_run_id_sets_run_id_missing_in_evidence(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected(run_id=None))
        assert received[0].payload["evidence"].get("run_id_missing") is True

    @pytest.mark.asyncio
    async def test_present_run_id_no_run_id_missing_in_evidence(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected(run_id=RUN_ID))
        assert received[0].payload["evidence"].get("run_id_missing") is None


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------

class TestAgentLifecycle:
    @pytest.mark.asyncio
    async def test_agent_running_after_start(self):
        from genus.core.agent import AgentState

        agent, bus = await _setup()
        assert agent.state == AgentState.RUNNING

    @pytest.mark.asyncio
    async def test_agent_stopped_after_stop(self):
        from genus.core.agent import AgentState

        agent, bus = await _setup()
        await agent.stop()
        assert agent.state == AgentState.STOPPED

    @pytest.mark.asyncio
    async def test_no_publish_after_stop(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await agent.stop()
        await bus.publish(_make_collected({"source": "x"}))
        assert received == []


# ---------------------------------------------------------------------------
# Custom policy
# ---------------------------------------------------------------------------

class TestCustomPolicy:
    @pytest.mark.asyncio
    async def test_custom_policy_applied(self):
        policy = SanitizationPolicy(
            policy_id="strict",
            allowed_keys=["source"],
        )
        agent, bus = await _setup(policy=policy)
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(
            _make_collected({"source": "dev", "metrics": {"temp": 20}, "extra": "drop"})
        )
        p = received[0].payload
        # Only "source" passes
        assert set(p["data"].keys()) == {"source"}
        assert "metrics" in p["evidence"]["removed_fields"]
        assert "extra" in p["evidence"]["removed_fields"]
        assert p["evidence"]["policy_id"] == "strict"

    @pytest.mark.asyncio
    async def test_default_policy_id_in_evidence(self):
        agent, bus = await _setup()
        received = []
        bus.subscribe(OUTPUT_TOPIC, "tl", lambda m: received.append(m))
        await bus.publish(_make_collected({"source": "x"}))
        assert received[0].payload["evidence"]["policy_id"] == "default"
        assert received[0].payload["evidence"]["policy_version"] == "p1-c1"
