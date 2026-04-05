"""
GENUS Security Module

Provides opt-in Topic ACL enforcement and a global Kill-Switch at the
MessageBus publish boundary.
"""

from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError

__all__ = [
    "TopicAclPolicy",
    "TopicPermissionError",
    "KillSwitch",
    "KillSwitchActiveError",
]
