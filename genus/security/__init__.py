"""
GENUS Security Module

Provides opt-in Topic ACL enforcement and a global Kill-Switch at the
MessageBus publish boundary.

Also exports ACL presets for common scenarios.
"""

from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError
from genus.security.acl_presets import default_orchestrator_toolexecutor_policy

__all__ = [
    "TopicAclPolicy",
    "TopicPermissionError",
    "KillSwitch",
    "KillSwitchActiveError",
    "default_orchestrator_toolexecutor_policy",
]
