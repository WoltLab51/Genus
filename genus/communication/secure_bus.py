"""
Secure Message Bus Wrapper

:class:`SecureMessageBus` wraps any message-bus implementation (either
:class:`~genus.communication.message_bus.MessageBus` or
:class:`~genus.communication.redis_message_bus.RedisMessageBus`) and enforces
the GENUS security boundary on every ``publish()`` call:

1. **Kill-switch check** – if a :class:`~genus.security.kill_switch.KillSwitch`
   is provided and active, :meth:`publish` raises
   :class:`~genus.security.kill_switch.KillSwitchActiveError` for any topic
   not on the kill-switch allowlist.
2. **Topic ACL check** – if ``acl_policy`` *and* ``acl_enforced=True`` are
   provided, :meth:`publish` raises
   :class:`~genus.security.topic_acl.TopicPermissionError` when the sender is
   not permitted to publish on the topic.

All other operations (``subscribe``, ``unsubscribe``, ``unsubscribe_all``,
``get_message_history``, ``connect``, ``close``) are delegated 1-to-1 to the
inner bus.

This makes the Redis-backed bus exactly as secure as the in-memory bus –
you only need to wrap it once at construction time, and all GENUS components
(Orchestrator, ToolExecutor, etc.) inherit the same security semantics
regardless of transport.

Usage::

    from genus.communication.redis_message_bus import RedisMessageBus
    from genus.communication.secure_bus import SecureMessageBus
    from genus.security.kill_switch import KillSwitch
    from genus.security.topic_acl import TopicAclPolicy

    ks = KillSwitch()
    policy = TopicAclPolicy()
    policy.allow("Orchestrator", "tool.call.requested")

    inner = RedisMessageBus(redis_url="redis://localhost:6379/0")
    await inner.connect()

    bus = SecureMessageBus(inner, kill_switch=ks, acl_policy=policy, acl_enforced=True)
    await bus.publish(some_message)  # checked against kill-switch + ACL
"""

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from genus.communication.message_bus import Message

if TYPE_CHECKING:
    from genus.security.kill_switch import KillSwitch
    from genus.security.topic_acl import TopicAclPolicy


class SecureMessageBus:
    """Security wrapper that enforces kill-switch and/or ACL on any bus.

    Args:
        inner_bus:    The underlying bus instance (``MessageBus`` or
                      ``RedisMessageBus``).  All non-security operations are
                      forwarded to it unchanged.
        kill_switch:  Optional :class:`~genus.security.kill_switch.KillSwitch`.
                      When provided and active, :meth:`publish` raises
                      :class:`~genus.security.kill_switch.KillSwitchActiveError`
                      for topics not on the allowlist.
        acl_policy:   Optional :class:`~genus.security.topic_acl.TopicAclPolicy`.
                      Checked only when *acl_enforced* is ``True``.
        acl_enforced: When ``True`` (and *acl_policy* is not ``None``),
                      :meth:`publish` raises
                      :class:`~genus.security.topic_acl.TopicPermissionError`
                      for unauthorised sender/topic combinations.
                      Default: ``False`` (permissive).
    """

    def __init__(
        self,
        inner_bus: Any,
        *,
        kill_switch: Optional["KillSwitch"] = None,
        acl_policy: Optional["TopicAclPolicy"] = None,
        acl_enforced: bool = False,
    ) -> None:
        self._inner = inner_bus
        self._kill_switch = kill_switch
        self._acl_policy = acl_policy
        self._acl_enforced = acl_enforced

    # ------------------------------------------------------------------
    # Security-checked publish
    # ------------------------------------------------------------------

    async def publish(self, message: Message) -> None:
        """Publish *message* after applying security checks.

        Security checks (in order):

        1. **Kill-switch**: raises
           :class:`~genus.security.kill_switch.KillSwitchActiveError` when
           active and topic not in allowlist.
        2. **ACL**: raises
           :class:`~genus.security.topic_acl.TopicPermissionError` when
           ``acl_enforced=True`` and sender is not permitted.

        Args:
            message: The message to publish.

        Raises:
            KillSwitchActiveError: When kill-switch is active and topic blocked.
            TopicPermissionError:  When ACL enforcement is active and sender
                                   is not permitted on the topic.
        """
        # 1) Kill-switch check
        if self._kill_switch is not None:
            self._kill_switch.check(message.topic)

        # 2) ACL check
        if self._acl_enforced and self._acl_policy is not None:
            if not self._acl_policy.is_allowed(message.sender_id, message.topic):
                from genus.security.topic_acl import TopicPermissionError
                raise TopicPermissionError(
                    sender_id=message.sender_id, topic=message.topic
                )

        await self._inner.publish(message)

    # ------------------------------------------------------------------
    # Pass-through subscription methods
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        subscriber_id: str,
        callback: Callable[[Message], Any],
    ) -> None:
        """Delegate to inner bus."""
        self._inner.subscribe(topic, subscriber_id, callback)

    def unsubscribe(self, topic: str, subscriber_id: str) -> None:
        """Delegate to inner bus."""
        self._inner.unsubscribe(topic, subscriber_id)

    def unsubscribe_all(self, subscriber_id: str) -> None:
        """Delegate to inner bus."""
        self._inner.unsubscribe_all(subscriber_id)

    # ------------------------------------------------------------------
    # Pass-through connection management (for Redis inner bus)
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Delegate to inner bus (no-op for in-memory bus)."""
        if hasattr(self._inner, "connect"):
            await self._inner.connect()

    async def close(self) -> None:
        """Delegate to inner bus (no-op for in-memory bus)."""
        if hasattr(self._inner, "close"):
            await self._inner.close()

    # ------------------------------------------------------------------
    # Pass-through history
    # ------------------------------------------------------------------

    def get_message_history(
        self, topic: Optional[str] = None, limit: int = 100
    ) -> List[Message]:
        """Delegate to inner bus."""
        return self._inner.get_message_history(topic=topic, limit=limit)
