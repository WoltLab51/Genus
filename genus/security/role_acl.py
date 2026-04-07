"""
Role-to-ACL bridge — P2

Provides a factory that builds a TopicAclPolicy from a role assignment
(actor_id → Role mapping).

This is the single place where roles are translated into ACL rules.
No other code should call policy.allow() for role-based permissions.

Usage::

    from genus.security.role_acl import build_policy_from_roles
    from genus.security.roles import Role

    policy = build_policy_from_roles({
        "collector-agent": Role.OPERATOR,
        "monitor-agent":   Role.READER,
        "admin-agent":     Role.ADMIN,
    })
    # inject into SecureMessageBus or TopicAclPolicy enforcement
"""

from typing import Dict

from genus.security.roles import Role, topics_for_role
from genus.security.topic_acl import TopicAclPolicy


def build_policy_from_roles(assignments: Dict[str, Role]) -> TopicAclPolicy:
    """Build a TopicAclPolicy from a role assignment mapping.

    Args:
        assignments: Dict mapping actor_id (str) to Role.

    Returns:
        A TopicAclPolicy with one allow() entry per (actor_id, topic) pair
        derived from the role's capability set.

    Example::

        policy = build_policy_from_roles({
            "collector": Role.OPERATOR,
            "viewer":    Role.READER,
        })
    """
    policy = TopicAclPolicy()
    for actor_id, role in assignments.items():
        for topic in topics_for_role(role):
            policy.allow(actor_id, topic)
    return policy
