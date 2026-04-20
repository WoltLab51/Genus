"""
Unit tests for genus.communication.secure_bus.SecureMessageBus

Tests run without Redis (in-memory bus only).

Verifies:
- Kill-switch active → publish raises KillSwitchActiveError
- Kill-switch inactive → publish passes through
- Kill-switch allowlist topic → publish passes through even when active
- ACL enforced + sender not allowed → publish raises TopicPermissionError
- ACL enforced + sender allowed → publish passes through
- ACL not enforced (default) → publish always passes through
- subscribe / unsubscribe / unsubscribe_all delegate to inner bus
- get_message_history delegates to inner bus
- connect/close delegate to inner bus (no-op for in-memory, present for Redis)
"""

import pytest

from genus.communication.message_bus import Message, MessageBus
from genus.communication.secure_bus import SecureMessageBus
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError
from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(topic: str = "tool.call.requested", sender_id: str = "TestSender") -> Message:
    return Message(topic=topic, payload={}, sender_id=sender_id)


# ---------------------------------------------------------------------------
# Kill-switch tests
# ---------------------------------------------------------------------------

class TestSecureBusKillSwitch:

    async def test_publish_blocked_when_kill_switch_active(self):
        ks = KillSwitch()
        ks.activate(reason="test emergency")
        bus = SecureMessageBus(MessageBus(), kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(_msg())

    async def test_publish_allowed_when_kill_switch_inactive(self):
        ks = KillSwitch()
        # not activated – should pass through
        bus = SecureMessageBus(MessageBus(), kill_switch=ks)
        await bus.publish(_msg())  # no exception

    async def test_publish_allowed_after_kill_switch_deactivated(self):
        ks = KillSwitch()
        ks.activate(reason="transient")
        ks.deactivate()
        bus = SecureMessageBus(MessageBus(), kill_switch=ks)
        await bus.publish(_msg())  # no exception

    async def test_allowlist_topic_passes_through_active_kill_switch(self):
        ks = KillSwitch(allowed_topics={"run.started"})
        ks.activate(reason="maintenance")
        bus = SecureMessageBus(MessageBus(), kill_switch=ks)

        # Allowlisted topic must pass
        await bus.publish(_msg(topic="run.started"))

    async def test_non_allowlist_topic_blocked_by_active_kill_switch(self):
        ks = KillSwitch(allowed_topics={"run.started"})
        ks.activate(reason="maintenance")
        bus = SecureMessageBus(MessageBus(), kill_switch=ks)

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(_msg(topic="tool.call.requested"))

    async def test_no_kill_switch_is_permissive(self):
        """Without a kill_switch argument, all publishes should pass."""
        bus = SecureMessageBus(MessageBus())
        await bus.publish(_msg())  # no exception


# ---------------------------------------------------------------------------
# ACL tests
# ---------------------------------------------------------------------------

class TestSecureBusAcl:

    async def test_publish_blocked_when_acl_enforced_and_not_allowed(self):
        policy = TopicAclPolicy()
        # No rules added → everything blocked when enforced
        bus = SecureMessageBus(MessageBus(), acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError):
            await bus.publish(_msg(sender_id="BadActor", topic="tool.call.requested"))

    async def test_publish_allowed_when_acl_enforced_and_sender_permitted(self):
        policy = TopicAclPolicy()
        policy.allow("Orchestrator", "tool.call.requested")
        bus = SecureMessageBus(MessageBus(), acl_policy=policy, acl_enforced=True)

        await bus.publish(_msg(sender_id="Orchestrator", topic="tool.call.requested"))

    async def test_publish_blocked_for_different_sender_same_topic(self):
        policy = TopicAclPolicy()
        policy.allow("Orchestrator", "tool.call.requested")
        bus = SecureMessageBus(MessageBus(), acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError):
            await bus.publish(_msg(sender_id="Intruder", topic="tool.call.requested"))

    async def test_acl_not_enforced_by_default(self):
        """Default acl_enforced=False → policy present but not checked."""
        policy = TopicAclPolicy()
        # No rules, but not enforced
        bus = SecureMessageBus(MessageBus(), acl_policy=policy)  # acl_enforced defaults False

        await bus.publish(_msg())  # no exception

    async def test_acl_not_enforced_when_no_policy(self):
        """With acl_enforced=True but no policy object, still permissive."""
        bus = SecureMessageBus(MessageBus(), acl_enforced=True)

        await bus.publish(_msg())  # no exception

    async def test_acl_error_carries_correct_sender_and_topic(self):
        policy = TopicAclPolicy()
        bus = SecureMessageBus(MessageBus(), acl_policy=policy, acl_enforced=True)

        with pytest.raises(TopicPermissionError) as exc_info:
            await bus.publish(_msg(sender_id="Alice", topic="run.started"))

        err = exc_info.value
        assert err.sender_id == "Alice"
        assert err.topic == "run.started"


# ---------------------------------------------------------------------------
# Kill-switch + ACL combined: kill-switch is checked first
# ---------------------------------------------------------------------------

class TestSecureBusKillSwitchBeforeAcl:

    async def test_kill_switch_checked_before_acl(self):
        """If kill-switch is active, KillSwitchActiveError must be raised
        even when the sender would pass ACL."""
        ks = KillSwitch()
        ks.activate(reason="emergency")
        policy = TopicAclPolicy()
        policy.allow("Orchestrator", "tool.call.requested")

        bus = SecureMessageBus(
            MessageBus(),
            kill_switch=ks,
            acl_policy=policy,
            acl_enforced=True,
        )

        with pytest.raises(KillSwitchActiveError):
            await bus.publish(_msg(sender_id="Orchestrator", topic="tool.call.requested"))


# ---------------------------------------------------------------------------
# Delegation: subscribe / unsubscribe / history
# ---------------------------------------------------------------------------

class TestSecureBusDelegation:

    async def test_message_delivered_to_subscriber(self):
        """Messages published via SecureMessageBus must reach subscribers."""
        inner = MessageBus()
        bus = SecureMessageBus(inner)

        received = []
        bus.subscribe("test.topic", "sub1", lambda m: received.append(m))
        await bus.publish(_msg(topic="test.topic"))

        assert len(received) == 1
        assert received[0].topic == "test.topic"

    async def test_unsubscribe_removes_subscriber(self):
        inner = MessageBus()
        bus = SecureMessageBus(inner)

        received = []
        bus.subscribe("test.topic", "sub1", lambda m: received.append(m))
        bus.unsubscribe("test.topic", "sub1")
        await bus.publish(_msg(topic="test.topic"))

        assert len(received) == 0

    async def test_unsubscribe_all_removes_all(self):
        inner = MessageBus()
        bus = SecureMessageBus(inner)

        received = []
        bus.subscribe("test.a", "sub1", lambda m: received.append(m))
        bus.subscribe("test.b", "sub1", lambda m: received.append(m))
        bus.unsubscribe_all("sub1")
        await bus.publish(_msg(topic="test.a"))
        await bus.publish(_msg(topic="test.b"))

        assert len(received) == 0

    async def test_get_message_history_delegates(self):
        inner = MessageBus()
        bus = SecureMessageBus(inner)

        await bus.publish(_msg(topic="hist.test"))
        history = bus.get_message_history(topic="hist.test")
        assert len(history) == 1
        assert history[0].topic == "hist.test"

    async def test_connect_close_no_op_for_in_memory(self):
        """connect/close should not raise for an in-memory inner bus."""
        inner = MessageBus()
        bus = SecureMessageBus(inner)
        await bus.connect()   # no-op
        await bus.close()     # no-op


# ---------------------------------------------------------------------------
# RedisMessageBus unit tests (no Redis required)
# ---------------------------------------------------------------------------

class TestRedisMessageBusSubscribe:
    """Unit tests for RedisMessageBus that do not require a Redis connection."""

    def test_wildcard_topic_raises_value_error(self):
        """subscribe() must raise ValueError for any topic containing '*'."""
        from genus.communication.redis_message_bus import RedisMessageBus

        bus = RedisMessageBus()
        with pytest.raises(ValueError, match="wildcard"):
            bus.subscribe("tool.call.*", "TestSub", lambda m: None)

    def test_wildcard_mid_segment_raises_value_error(self):
        from genus.communication.redis_message_bus import RedisMessageBus

        bus = RedisMessageBus()
        with pytest.raises(ValueError, match="wildcard"):
            bus.subscribe("*.call.requested", "TestSub", lambda m: None)

    async def test_exact_topic_subscribe_does_not_raise(self):
        """subscribe() with an exact topic (no '*') must not raise."""
        from genus.communication.redis_message_bus import RedisMessageBus

        bus = RedisMessageBus()
        # Should not raise — Redis channel subscription will be deferred
        # via asyncio.ensure_future, but the sync part must succeed.
        try:
            bus.subscribe("tool.call.requested", "TestSub", lambda m: None)
        except ValueError:
            pytest.fail("subscribe() raised ValueError for an exact topic")
