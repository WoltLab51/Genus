"""
Tests for P2 Security Slice: Topic ACL + Kill-Switch

Covers:
- TopicAclPolicy: allow/revoke/is_allowed
- KillSwitch: activate/deactivate/check
- MessageBus default mode (permissive – existing pipeline must not break)
- MessageBus with ACL enforcement
- MessageBus with kill-switch
- QM pipeline integration (analysis.completed -> quality.scored -> decision.made)
"""

import pytest
import asyncio

from genus.communication.message_bus import MessageBus, Message
from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError


# ---------------------------------------------------------------------------
# TopicAclPolicy unit tests
# ---------------------------------------------------------------------------

class TestTopicAclPolicy:
    def test_allow_and_is_allowed(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        assert policy.is_allowed("agent-1", "topic.a") is True

    def test_is_not_allowed_unknown_sender(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        assert policy.is_allowed("agent-2", "topic.a") is False

    def test_is_not_allowed_unknown_topic(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        assert policy.is_allowed("agent-1", "topic.b") is False

    def test_revoke_removes_permission(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        policy.revoke("agent-1", "topic.a")
        assert policy.is_allowed("agent-1", "topic.a") is False

    def test_revoke_noop_on_unknown(self):
        policy = TopicAclPolicy()
        # Must not raise
        policy.revoke("nobody", "topic.a")

    def test_multiple_topics_per_sender(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        policy.allow("agent-1", "topic.b")
        assert policy.is_allowed("agent-1", "topic.a") is True
        assert policy.is_allowed("agent-1", "topic.b") is True
        assert policy.is_allowed("agent-1", "topic.c") is False

    def test_exact_match_only_no_wildcard(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.*")
        # Should NOT match 'topic.a' – this is exact match only
        assert policy.is_allowed("agent-1", "topic.a") is False
        assert policy.is_allowed("agent-1", "topic.*") is True

    def test_empty_policy_allows_nothing(self):
        policy = TopicAclPolicy()
        assert policy.is_allowed("agent-1", "anything") is False

    def test_topic_permission_error_message(self):
        err = TopicPermissionError("my-agent", "some.topic")
        assert "my-agent" in str(err)
        assert "some.topic" in str(err)
        assert err.sender_id == "my-agent"
        assert err.topic == "some.topic"


# ---------------------------------------------------------------------------
# KillSwitch unit tests
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_initially_inactive(self):
        ks = KillSwitch()
        assert ks.is_active() is False

    def test_activate_sets_active(self):
        ks = KillSwitch()
        ks.activate(reason="maintenance", actor="ops")
        assert ks.is_active() is True
        assert ks.reason == "maintenance"
        assert ks.actor == "ops"

    def test_deactivate_restores_inactive(self):
        ks = KillSwitch()
        ks.activate(reason="test")
        ks.deactivate(actor="ops")
        assert ks.is_active() is False

    def test_check_raises_when_active(self):
        ks = KillSwitch()
        ks.activate(reason="emergency")
        with pytest.raises(KillSwitchActiveError) as exc_info:
            ks.check("analysis.completed")
        assert exc_info.value.topic == "analysis.completed"
        assert "emergency" in str(exc_info.value)

    def test_check_passes_when_inactive(self):
        ks = KillSwitch()
        # Must not raise
        ks.check("analysis.completed")

    def test_check_passes_for_allowlist_topic_when_active(self):
        ks = KillSwitch(allowed_topics={"health.ping"})
        ks.activate(reason="maintenance")
        # Must not raise for allowlisted topic
        ks.check("health.ping")

    def test_check_raises_for_non_allowlist_topic_when_active(self):
        ks = KillSwitch(allowed_topics={"health.ping"})
        ks.activate(reason="maintenance")
        with pytest.raises(KillSwitchActiveError):
            ks.check("quality.scored")

    def test_allowed_topics_property_returns_copy(self):
        ks = KillSwitch(allowed_topics={"a", "b"})
        topics = ks.allowed_topics
        topics.add("c")
        # Internal state must not be modified
        assert "c" not in ks.allowed_topics

    def test_kill_switch_active_error_fields(self):
        err = KillSwitchActiveError("my.topic", "reason text")
        assert err.topic == "my.topic"
        assert err.reason == "reason text"
        assert "my.topic" in str(err)
        assert "reason text" in str(err)


# ---------------------------------------------------------------------------
# MessageBus default mode (permissive) – existing pipeline must not break
# ---------------------------------------------------------------------------

class TestMessageBusDefaultPermissive:
    """All pre-existing behaviour must work without any security config."""

    @pytest.mark.asyncio
    async def test_publish_without_acl_or_kill_switch(self):
        bus = MessageBus()
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("topic.a", "sub-1", cb)
        await bus.publish(Message(topic="topic.a", payload={}, sender_id="any-agent"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_permissive_mode_ignores_acl_policy_when_not_enforced(self):
        policy = TopicAclPolicy()
        # policy allows nothing – but enforcement is OFF by default
        bus = MessageBus(acl_policy=policy, acl_enforced=False)
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("topic.a", "sub", cb)
        # Must not raise even though policy allows nothing
        await bus.publish(Message(topic="topic.a", payload={}, sender_id="any-agent"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_permissive_mode_no_kill_switch(self):
        bus = MessageBus()
        # Must not raise
        await bus.publish(Message(topic="quality.scored", payload={}, sender_id="qa"))


# ---------------------------------------------------------------------------
# MessageBus with ACL enforcement
# ---------------------------------------------------------------------------

class TestMessageBusAclEnforcement:
    @pytest.mark.asyncio
    async def test_allowed_sender_topic_passes(self):
        policy = TopicAclPolicy()
        policy.allow("QualityAgent-1", "quality.scored")
        bus = MessageBus(acl_policy=policy, acl_enforced=True)
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("quality.scored", "sub", cb)
        await bus.publish(
            Message(topic="quality.scored", payload={}, sender_id="QualityAgent-1")
        )
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_unauthorised_sender_raises(self):
        policy = TopicAclPolicy()
        policy.allow("QualityAgent-1", "quality.scored")
        bus = MessageBus(acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError) as exc_info:
            await bus.publish(
                Message(
                    topic="quality.scored",
                    payload={},
                    sender_id="EvilAgent",
                )
            )
        assert exc_info.value.sender_id == "EvilAgent"
        assert exc_info.value.topic == "quality.scored"

    @pytest.mark.asyncio
    async def test_unauthorised_topic_raises(self):
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        bus = MessageBus(acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError):
            await bus.publish(
                Message(topic="topic.b", payload={}, sender_id="agent-1")
            )

    @pytest.mark.asyncio
    async def test_acl_error_message_not_stored_in_history(self):
        """A rejected message must not enter message history."""
        policy = TopicAclPolicy()
        bus = MessageBus(acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError):
            await bus.publish(
                Message(topic="any.topic", payload={}, sender_id="bad-agent")
            )
        assert len(bus.get_message_history()) == 0


# ---------------------------------------------------------------------------
# MessageBus with kill-switch
# ---------------------------------------------------------------------------

class TestMessageBusKillSwitch:
    @pytest.mark.asyncio
    async def test_inactive_kill_switch_does_not_block(self):
        ks = KillSwitch()
        bus = MessageBus(kill_switch=ks)
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("quality.scored", "sub", cb)
        await bus.publish(
            Message(topic="quality.scored", payload={}, sender_id="qa")
        )
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_active_kill_switch_blocks_publish(self):
        ks = KillSwitch()
        ks.activate(reason="emergency stop")
        bus = MessageBus(kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(
                Message(topic="quality.scored", payload={}, sender_id="qa")
            )

    @pytest.mark.asyncio
    async def test_active_kill_switch_allows_allowlist_topic(self):
        ks = KillSwitch(allowed_topics={"health.ping"})
        ks.activate(reason="maintenance")
        bus = MessageBus(kill_switch=ks)
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("health.ping", "sub", cb)
        # Must not raise
        await bus.publish(
            Message(topic="health.ping", payload={}, sender_id="monitor")
        )
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_deactivate_restores_normal_publish(self):
        ks = KillSwitch()
        ks.activate(reason="test")
        bus = MessageBus(kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(Message(topic="t", payload={}, sender_id="a"))

        ks.deactivate()
        received = []

        async def cb(msg):
            received.append(msg)

        bus.subscribe("t", "sub", cb)
        await bus.publish(Message(topic="t", payload={}, sender_id="a"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_kill_switch_checked_before_acl(self):
        """Kill-switch takes precedence over ACL check."""
        policy = TopicAclPolicy()
        policy.allow("agent-1", "topic.a")
        ks = KillSwitch()
        ks.activate(reason="priority test")
        bus = MessageBus(acl_policy=policy, acl_enforced=True, kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(
                Message(topic="topic.a", payload={}, sender_id="agent-1")
            )

    @pytest.mark.asyncio
    async def test_kill_switch_blocked_message_not_in_history(self):
        ks = KillSwitch()
        ks.activate(reason="test")
        bus = MessageBus(kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(Message(topic="t", payload={}, sender_id="a"))

        assert len(bus.get_message_history()) == 0


# ---------------------------------------------------------------------------
# QM pipeline integration – default permissive mode
# ---------------------------------------------------------------------------

class TestQmPipelineDefaultMode:
    """Integration-style unit test ensuring the QM pipeline remains
    functional in default (permissive) mode without any security config."""

    @pytest.mark.asyncio
    async def test_analysis_completed_quality_scored_decision_made(self):
        from genus.agents.quality_agent import QualityAgent
        from genus.agents.decision_agent import DecisionAgent

        bus = MessageBus()  # default – no ACL, no kill-switch

        quality_agent = QualityAgent(message_bus=bus, agent_id="QualityAgent-1")
        decision_agent = DecisionAgent(message_bus=bus, agent_id="DecisionAgent-1")

        await quality_agent.initialize()
        await quality_agent.start()
        await decision_agent.initialize()
        await decision_agent.start()

        decisions = []

        async def capture_decision(msg):
            decisions.append(msg)

        bus.subscribe("decision.made", "test-listener", capture_decision)

        # Publish a high-quality analysis result
        analysis_msg = Message(
            topic="analysis.completed",
            payload={"quality_score": 0.92},
            sender_id="AnalysisAgent-1",
            metadata={"run_id": "test-run-001"},
        )
        await bus.publish(analysis_msg)
        # Allow async callbacks to propagate
        await asyncio.sleep(0.05)

        assert len(decisions) >= 1, "DecisionAgent must publish decision.made"
        decision_payload = decisions[0].payload
        assert decision_payload["decision"] in {"accept", "retry", "replan", "escalate", "delegate"}

        await quality_agent.stop()
        await decision_agent.stop()


# ---------------------------------------------------------------------------
# QM pipeline with ACL enforcement
# ---------------------------------------------------------------------------

class TestQmPipelineAclEnforced:
    """Verify QualityAgent pipeline works when ACL is enforced with correct
    permissions, and that an unauthorised sender is blocked."""

    @pytest.mark.asyncio
    async def test_quality_agent_allowed_to_publish_quality_scored(self):
        from genus.agents.quality_agent import QualityAgent

        policy = TopicAclPolicy()

        # We must allow every sender that will publish within the pipeline
        # AnalysisAgent publishes analysis.completed; QualityAgent publishes quality.scored
        bus_pre = MessageBus()  # permissive bus just to get the agent's ID
        qa_id_probe = QualityAgent(message_bus=bus_pre, agent_id="QualityAgent-E2E")

        policy.allow("AnalysisAgent-E2E", "analysis.completed")
        policy.allow(qa_id_probe.id, "quality.scored")

        bus = MessageBus(acl_policy=policy, acl_enforced=True)
        quality_agent = QualityAgent(message_bus=bus, agent_id="QualityAgent-E2E")

        await quality_agent.initialize()
        await quality_agent.start()

        scored = []

        async def capture(msg):
            scored.append(msg)

        bus.subscribe("quality.scored", "listener", capture)

        await bus.publish(
            Message(
                topic="analysis.completed",
                payload={"quality_score": 0.85},
                sender_id="AnalysisAgent-E2E",
                metadata={"run_id": "test-run-acl"},
            )
        )
        await asyncio.sleep(0.05)

        assert len(scored) == 1
        assert scored[0].payload["quality_score"] == pytest.approx(0.85)

        await quality_agent.stop()

    @pytest.mark.asyncio
    async def test_unauthorised_sender_blocked_in_enforced_mode(self):
        policy = TopicAclPolicy()
        # No rules added – everything is denied
        bus = MessageBus(acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError):
            await bus.publish(
                Message(
                    topic="quality.scored",
                    payload={},
                    sender_id="UnauthorisedAgent",
                )
            )
