"""
Kill-Switch

Global emergency stop mechanism for the MessageBus publish boundary.

When the kill-switch is active, MessageBus.publish() raises
KillSwitchActiveError for every topic that is not on the allowlist.

Design notes:
- Pure in-memory; no file I/O or network calls.
- Thread-safe via simple attribute assignment (GIL is sufficient here).
- The allowlist defaults to empty (no topic passes through when active).
- Deactivating restores normal publish behaviour immediately.
"""

from typing import Optional, Set


class KillSwitchActiveError(Exception):
    """Raised by MessageBus.publish() when the kill-switch is active.

    Only raised for topics that are *not* in the allowlist configured on
    the KillSwitch instance.
    """

    def __init__(self, topic: str, reason: str) -> None:
        self.topic = topic
        self.reason = reason
        super().__init__(
            "Kill-switch is active (reason: '{}'); publish blocked for topic '{}'".format(
                reason, topic
            )
        )


class KillSwitch:
    """Global kill-switch for the MessageBus publish boundary.

    Usage::

        ks = KillSwitch()

        # Activate – blocks all publish() calls except the allowlist
        ks.activate(reason="emergency stop", actor="ops-team")

        ks.is_active()   # True

        # Restore normal operation
        ks.deactivate(actor="ops-team")

        ks.is_active()   # False

    Allowlist topics::

        ks = KillSwitch(allowed_topics={"health.ping"})
        ks.activate(reason="maintenance")
        # MessageBus.publish(topic="health.ping", ...) still succeeds
        # MessageBus.publish(topic="analysis.completed", ...) raises KillSwitchActiveError

    Note: When the kill-switch is active it will *also* block QualityAgent
    and DecisionAgent from publishing.  This is intentional – an active
    kill-switch means the system is in emergency stop mode.
    """

    def __init__(self, allowed_topics: Optional[Set[str]] = None) -> None:
        """
        Args:
            allowed_topics: Topics that bypass the kill-switch when active.
                            Defaults to an empty set (all topics blocked).
        """
        self._active: bool = False
        self._reason: str = ""
        self._actor: Optional[str] = None
        self._allowed_topics: Set[str] = set(allowed_topics) if allowed_topics else set()

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def activate(self, reason: str, actor: Optional[str] = None) -> None:
        """Activate the kill-switch.

        Args:
            reason: Human-readable reason for activation (stored for audit).
            actor: Optional identifier of who activated the switch.
        """
        self._active = True
        self._reason = reason
        self._actor = actor

    def deactivate(self, actor: Optional[str] = None) -> None:
        """Deactivate the kill-switch, restoring normal publish behaviour.

        Args:
            actor: Optional identifier of who deactivated the switch.
        """
        self._active = False
        self._actor = actor

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """Return True when the kill-switch is active."""
        return self._active

    @property
    def reason(self) -> str:
        """The reason provided when the switch was last activated."""
        return self._reason

    @property
    def actor(self) -> Optional[str]:
        """The actor who last changed the switch state."""
        return self._actor

    @property
    def allowed_topics(self) -> Set[str]:
        """The set of topics that bypass the kill-switch."""
        return set(self._allowed_topics)

    # ------------------------------------------------------------------
    # Internal helper used by MessageBus
    # ------------------------------------------------------------------

    def check(self, topic: str) -> None:
        """Raise KillSwitchActiveError if the switch is active and *topic*
        is not in the allowlist.

        This method is called by MessageBus.publish(); application code
        should not call it directly.

        Args:
            topic: The topic being published.

        Raises:
            KillSwitchActiveError: When active and topic not in allowlist.
        """
        if self._active and topic not in self._allowed_topics:
            raise KillSwitchActiveError(topic=topic, reason=self._reason)
