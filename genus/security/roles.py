"""
GENUS Role Model — P2

Defines roles as capability bundles. A role determines which topics
an actor is allowed to publish on the MessageBus.

Design principles (GENUS-2.0)
------------------------------
- **Roles = Capabilities**: A role is a named set of allowed topics.
  It does NOT represent a person or user type.
- **Central definition**: All role-to-topic mappings live here.
  Nothing is scattered across agents or handlers.
- **Additive**: Roles can be combined. Admin = Operator + Admin-extras.
- **No inheritance hierarchy**: Roles are flat sets, not class trees.
  Composition over inheritance.

Roles
-----
- ``Role.READER``   — read-only: can observe system events, no writes
- ``Role.OPERATOR`` — standard: can start runs, submit feedback
- ``Role.ADMIN``    — full: can trigger kill-switch, modify ACL

Usage::

    from genus.security.roles import Role, topics_for_role
    from genus.security.topic_acl import TopicAclPolicy

    policy = TopicAclPolicy()
    for topic in topics_for_role(Role.OPERATOR):
        policy.allow("my-agent-id", topic)
"""

from enum import Enum, auto
from typing import Dict, FrozenSet, Tuple


class Role(Enum):
    """Named capability level for GENUS actors."""
    READER = auto()
    OPERATOR = auto()
    ADMIN = auto()


# ---------------------------------------------------------------------------
# Capability sets per role
# ---------------------------------------------------------------------------

# Topics a READER may publish (observability only — no side-effects)
_READER_TOPICS: FrozenSet[str] = frozenset()

# Topics an OPERATOR may publish (run control + feedback)
_OPERATOR_TOPICS: FrozenSet[str] = frozenset({
    "run.started",
    "run.completed",
    "run.failed",
    "data.collected",
    "outcome.recorded",
})

# Topics an ADMIN may publish (everything Operator can + admin controls)
_ADMIN_TOPICS: FrozenSet[str] = _OPERATOR_TOPICS | frozenset({
    "system.kill_switch.activated",
    "system.kill_switch.deactivated",
    "system.acl.updated",
})

_ROLE_TOPICS: Dict[Role, FrozenSet[str]] = {
    Role.READER: _READER_TOPICS,
    Role.OPERATOR: _OPERATOR_TOPICS,
    Role.ADMIN: _ADMIN_TOPICS,
}


def topics_for_role(role: Role) -> FrozenSet[str]:
    """Return the set of topics an actor with *role* may publish.

    Args:
        role: The role to look up.

    Returns:
        Frozenset of allowed topic strings.
    """
    return _ROLE_TOPICS[role]


def all_roles() -> Tuple[Role, ...]:
    """Return all defined roles in ascending privilege order."""
    return (Role.READER, Role.OPERATOR, Role.ADMIN)
