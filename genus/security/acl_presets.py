"""
ACL Presets for GENUS Security

Provides predefined TopicAclPolicy configurations for common scenarios.
These presets make it easy to enforce standard security policies without
manually configuring every rule.

Example usage::

    from genus.security.acl_presets import default_orchestrator_toolexecutor_policy
    from genus.communication.secure_bus import SecureMessageBus

    policy = default_orchestrator_toolexecutor_policy()
    bus = SecureMessageBus(inner_bus, acl_policy=policy, acl_enforced=True)
"""

from genus.security.topic_acl import TopicAclPolicy
from genus.run import topics as run_topics
from genus.tools import topics as tool_topics


def default_orchestrator_toolexecutor_policy() -> TopicAclPolicy:
    """Create a default ACL policy for Orchestrator and ToolExecutor.

    This policy allows:
    - Orchestrator to publish: run.* topics and tool.call.requested
    - ToolExecutor to publish: tool.call.succeeded and tool.call.failed

    Note: This uses exact topic matching only, as TopicAclPolicy does not
    support wildcards. Each run.* topic must be added explicitly.

    Returns:
        A TopicAclPolicy configured for standard Orchestrator/ToolExecutor interaction.
    """
    policy = TopicAclPolicy()

    # Orchestrator permissions
    orchestrator_id = "Orchestrator"
    policy.allow(orchestrator_id, run_topics.RUN_STARTED)
    policy.allow(orchestrator_id, run_topics.RUN_COMPLETED)
    policy.allow(orchestrator_id, run_topics.RUN_FAILED)
    policy.allow(orchestrator_id, run_topics.RUN_STEP_PLANNED)
    policy.allow(orchestrator_id, run_topics.RUN_STEP_STARTED)
    policy.allow(orchestrator_id, run_topics.RUN_STEP_COMPLETED)
    policy.allow(orchestrator_id, run_topics.RUN_STEP_FAILED)
    policy.allow(orchestrator_id, tool_topics.TOOL_CALL_REQUESTED)

    # ToolExecutor permissions
    tool_executor_id = "ToolExecutor"
    policy.allow(tool_executor_id, tool_topics.TOOL_CALL_SUCCEEDED)
    policy.allow(tool_executor_id, tool_topics.TOOL_CALL_FAILED)

    return policy
