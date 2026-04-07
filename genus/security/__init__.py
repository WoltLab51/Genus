"""
GENUS Security Module

Provides opt-in Topic ACL enforcement and a global Kill-Switch at the
MessageBus publish boundary.

Also exports ACL presets for common scenarios and input sanitization utilities.
"""

from genus.security.topic_acl import TopicAclPolicy, TopicPermissionError
from genus.security.kill_switch import KillSwitch, KillSwitchActiveError, DEFAULT_KILL_SWITCH
from genus.security.acl_presets import default_orchestrator_toolexecutor_policy, default_pipeline_policy
from genus.security.sanitization import SanitizationPolicy, sanitize_payload, DEFAULT_POLICY
from genus.security.roles import Role, topics_for_role
from genus.security.role_acl import build_policy_from_roles

__all__ = [
    "TopicAclPolicy",
    "TopicPermissionError",
    "KillSwitch",
    "KillSwitchActiveError",
    "DEFAULT_KILL_SWITCH",
    "default_orchestrator_toolexecutor_policy",
    "default_pipeline_policy",
    "SanitizationPolicy",
    "sanitize_payload",
    "DEFAULT_POLICY",
    "Role",
    "topics_for_role",
    "build_policy_from_roles",
]
