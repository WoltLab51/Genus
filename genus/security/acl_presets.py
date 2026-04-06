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
    - Orchestrator to publish: all run lifecycle topics (derived from
      ``run_topics.ALL_RUN_TOPICS``) and ``tool.call.requested``
    - ToolExecutor to publish: ``tool.call.succeeded`` and ``tool.call.failed``

    Note: This uses exact topic matching only, as TopicAclPolicy does not
    support wildcards.  The allowed run topics are derived from
    ``genus.run.topics.ALL_RUN_TOPICS`` so that adding a new run-lifecycle
    constant there automatically keeps this preset complete.

    Returns:
        A TopicAclPolicy configured for standard Orchestrator/ToolExecutor interaction.
    """
    policy = TopicAclPolicy()

    # Orchestrator permissions – derived from ALL_RUN_TOPICS so future
    # additions to the run-lifecycle topic constants are covered automatically.
    orchestrator_id = "Orchestrator"
    for topic in run_topics.ALL_RUN_TOPICS:
        policy.allow(orchestrator_id, topic)
    policy.allow(orchestrator_id, tool_topics.TOOL_CALL_REQUESTED)

    # ToolExecutor permissions
    tool_executor_id = "ToolExecutor"
    policy.allow(tool_executor_id, tool_topics.TOOL_CALL_SUCCEEDED)
    policy.allow(tool_executor_id, tool_topics.TOOL_CALL_FAILED)

    return policy
