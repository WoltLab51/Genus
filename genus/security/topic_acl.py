"""
Topic ACL Policy

Provides opt-in, exact-match topic access control for the MessageBus.
By default the MessageBus operates in permissive mode; enforcement is
only activated when a TopicAclPolicy is injected and acl_enforced=True.
"""

from typing import Dict, Set


class TopicPermissionError(Exception):
    """Raised when a sender is not allowed to publish on a topic.

    Only raised when ACL enforcement is active (acl_enforced=True on the
    MessageBus).  In the default permissive mode this exception is never
    raised.
    """

    def __init__(self, sender_id: str, topic: str) -> None:
        self.sender_id = sender_id
        self.topic = topic
        super().__init__(
            "Sender '{}' is not allowed to publish on topic '{}'".format(
                sender_id, topic
            )
        )


class TopicAclPolicy:
    """Exact-match topic ACL policy.

    Maps each ``sender_id`` to the set of topics it is allowed to publish on.
    Topic matching is *exact* (no regex, no wildcards) for predictability.

    Usage::

        policy = TopicAclPolicy()
        policy.allow("QualityAgent-1", "quality.scored")
        policy.allow("QualityAgent-1", "analysis.completed")

        policy.is_allowed("QualityAgent-1", "quality.scored")   # True
        policy.is_allowed("QualityAgent-1", "decision.made")    # False
        policy.is_allowed("UnknownAgent",   "quality.scored")   # False

    An empty policy allows nothing, so always add entries before enforcing.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def allow(self, sender_id: str, topic: str) -> None:
        """Grant *sender_id* permission to publish on *topic*.

        Args:
            sender_id: The agent/sender identifier.
            topic: The exact topic string the sender may publish on.
        """
        if sender_id not in self._rules:
            self._rules[sender_id] = set()
        self._rules[sender_id].add(topic)

    def revoke(self, sender_id: str, topic: str) -> None:
        """Remove publish permission for *sender_id* on *topic*.

        A no-op if the permission did not exist.

        Args:
            sender_id: The agent/sender identifier.
            topic: The exact topic string to revoke.
        """
        if sender_id in self._rules:
            self._rules[sender_id].discard(topic)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_allowed(self, sender_id: str, topic: str) -> bool:
        """Return True if *sender_id* may publish on *topic*.

        Uses exact matching only.

        Args:
            sender_id: The agent/sender identifier.
            topic: The topic to check.

        Returns:
            True when an explicit allow rule exists, False otherwise.
        """
        allowed_topics = self._rules.get(sender_id, set())
        return topic in allowed_topics
