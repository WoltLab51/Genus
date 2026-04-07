"""
GENUS Security Module

Provides opt-in Topic ACL enforcement and a global Kill-Switch at the
MessageBus publish boundary.

Also exports ACL presets for common scenarios and input sanitization utilities.
"""

from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError, DEFAULT_KILL_SWITCH
from genus.security.acl_presets import default_orchestrator_toolexecutor_policy
from genus.security.sanitization import SanitizationPolicy, sanitize_payload, DEFAULT_POLICY

__all__ = [
    "TopicAclPolicy",
    "TopicPermissionError",
    "KillSwitch",
    "KillSwitchActiveError",
    "DEFAULT_KILL_SWITCH",
    "default_orchestrator_toolexecutor_policy",
    "SanitizationPolicy",
    "sanitize_payload",
    "DEFAULT_POLICY",
]
