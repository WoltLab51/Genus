"""
Default Topic Registry

Provides a pre-populated ``DEFAULT_REGISTRY`` instance that consolidates all
known GENUS topics from every domain-specific ``topics.py`` file.

This is the single authoritative source of topic ownership and metadata.
Import ``DEFAULT_REGISTRY`` wherever you need to validate or inspect topics::

    from genus.communication.topics import DEFAULT_REGISTRY

    DEFAULT_REGISTRY.assert_registered("quality.scored")
    entries = DEFAULT_REGISTRY.topics_for_domain("run")

The ``MessageBus`` does *not* use this registry internally; topic validation is
opt-in for modules that require strict governance.
"""

from __future__ import annotations

from genus.communication.topic_registry import TopicEntry, TopicRegistry

DEFAULT_REGISTRY = TopicRegistry()

_r = DEFAULT_REGISTRY.register  # shorthand


# ---------------------------------------------------------------------------
# tools domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="tool.call.requested",
    owner="Orchestrator",
    direction="publish",
    domain="tools",
    description="Orchestrator requests a tool call from a tool-executor agent.",
))
_r(TopicEntry(
    topic="tool.call.succeeded",
    owner="ToolExecutorAgent",
    direction="publish",
    domain="tools",
    description="Tool-executor reports successful tool execution.",
))
_r(TopicEntry(
    topic="tool.call.failed",
    owner="ToolExecutorAgent",
    direction="publish",
    domain="tools",
    description="Tool-executor reports failed tool execution.",
))

# ---------------------------------------------------------------------------
# dev domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="dev.loop.started",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Dev loop has started for a given run.",
))
_r(TopicEntry(
    topic="dev.loop.completed",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Dev loop completed successfully.",
))
_r(TopicEntry(
    topic="dev.loop.failed",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Dev loop terminated with a failure.",
))
_r(TopicEntry(
    topic="dev.plan.requested",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Planning phase requested.",
))
_r(TopicEntry(
    topic="dev.plan.completed",
    owner="PlannerAgent",
    direction="publish",
    domain="dev",
    description="Planning phase completed.",
))
_r(TopicEntry(
    topic="dev.plan.failed",
    owner="PlannerAgent",
    direction="publish",
    domain="dev",
    description="Planning phase failed.",
))
_r(TopicEntry(
    topic="dev.implement.requested",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Implementation phase requested.",
))
_r(TopicEntry(
    topic="dev.implement.completed",
    owner="ImplementerAgent",
    direction="publish",
    domain="dev",
    description="Implementation phase completed.",
))
_r(TopicEntry(
    topic="dev.implement.failed",
    owner="ImplementerAgent",
    direction="publish",
    domain="dev",
    description="Implementation phase failed.",
))
_r(TopicEntry(
    topic="dev.test.requested",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Testing phase requested.",
))
_r(TopicEntry(
    topic="dev.test.completed",
    owner="TesterAgent",
    direction="publish",
    domain="dev",
    description="Testing phase completed.",
))
_r(TopicEntry(
    topic="dev.test.failed",
    owner="TesterAgent",
    direction="publish",
    domain="dev",
    description="Testing phase failed.",
))
_r(TopicEntry(
    topic="dev.fix.requested",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Fix phase requested.",
))
_r(TopicEntry(
    topic="dev.fix.completed",
    owner="FixerAgent",
    direction="publish",
    domain="dev",
    description="Fix phase completed.",
))
_r(TopicEntry(
    topic="dev.fix.failed",
    owner="FixerAgent",
    direction="publish",
    domain="dev",
    description="Fix phase failed.",
))
_r(TopicEntry(
    topic="dev.review.requested",
    owner="DevLoopOrchestrator",
    direction="publish",
    domain="dev",
    description="Review phase requested.",
))
_r(TopicEntry(
    topic="dev.review.completed",
    owner="ReviewerAgent",
    direction="publish",
    domain="dev",
    description="Review phase completed.",
))
_r(TopicEntry(
    topic="dev.review.failed",
    owner="ReviewerAgent",
    direction="publish",
    domain="dev",
    description="Review phase failed.",
))

# ---------------------------------------------------------------------------
# meta domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="meta.evaluation.completed",
    owner="EvaluationAgent",
    direction="publish",
    domain="meta",
    description="Run evaluation completed and artifact saved.",
))

# ---------------------------------------------------------------------------
# feedback domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="outcome.recorded",
    owner="OutcomeRecorder",
    direction="publish",
    domain="feedback",
    description="User/operator submitted outcome feedback for a run.",
))
_r(TopicEntry(
    topic="feedback.received",
    owner="FeedbackAgent",
    direction="publish",
    domain="feedback",
    description="FeedbackAgent has journaled feedback and updated strategy scores.",
))

# ---------------------------------------------------------------------------
# run domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="run.started",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="A new run has started.",
))
_r(TopicEntry(
    topic="run.step.planned",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="A run step has been planned.",
))
_r(TopicEntry(
    topic="run.step.started",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="A run step has started execution.",
))
_r(TopicEntry(
    topic="run.step.completed",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="A run step completed successfully.",
))
_r(TopicEntry(
    topic="run.step.failed",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="A run step failed.",
))
_r(TopicEntry(
    topic="run.completed",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="The run completed successfully.",
))
_r(TopicEntry(
    topic="run.failed",
    owner="Orchestrator",
    direction="publish",
    domain="run",
    description="The run terminated with a failure.",
))

# ---------------------------------------------------------------------------
# quality domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="analysis.completed",
    owner="AnalysisAgent",
    direction="publish",
    domain="quality",
    description="Analysis phase completed; payload carries classification and confidence.",
))
_r(TopicEntry(
    topic="data.analyzed",
    owner="AnalysisAgent",
    direction="publish",
    domain="quality",
    description="Alias for analysis.completed used by some legacy consumers.",
    stable=False,
))
_r(TopicEntry(
    topic="quality.scored",
    owner="QualityAgent",
    direction="publish",
    domain="quality",
    description="Quality evaluation completed; payload carries quality_score, dimensions, evidence.",
))

# ---------------------------------------------------------------------------
# growth domain
# ---------------------------------------------------------------------------

_r(TopicEntry(
    topic="need.identified",
    owner="NeedObserver",
    direction="publish",
    domain="growth",
    description="NeedObserver hat einen wiederkehrenden Need erkannt der einen Build rechtfertigt.",
))
_r(TopicEntry(
    topic="need.rejected",
    owner="GrowthOrchestrator",
    direction="publish",
    domain="growth",
    description="GrowthOrchestrator hat einen Need abgelehnt (Cooldown, QualityGate, oder StabilityRules).",
))
_r(TopicEntry(
    topic="growth.build.requested",
    owner="GrowthOrchestrator",
    direction="publish",
    domain="growth",
    description="GrowthOrchestrator fordert einen neuen Agent-Build vom DevLoopOrchestrator an.",
))
_r(TopicEntry(
    topic="agent.bootstrapped",
    owner="AgentBootstrapper",
    direction="publish",
    domain="growth",
    description="AgentBootstrapper hat einen neuen Agenten erfolgreich integriert.",
))
_r(TopicEntry(
    topic="agent.deprecated",
    owner="AgentBootstrapper",
    direction="publish",
    domain="growth",
    description="AgentBootstrapper hat einen alten Agenten als deprecated markiert.",
))
_r(TopicEntry(
    topic="agent.bootstrap_failed",
    owner="AgentBootstrapper",
    direction="publish",
    domain="growth",
    description="AgentBootstrapper konnte den generierten Agenten-Code nicht importieren.",
))
_r(TopicEntry(
    topic="agent.start.failed",
    owner="AgentBootstrapper",
    direction="publish",
    domain="growth",
    description="AgentBootstrapper konnte einen generierten Agenten nicht initialisieren oder starten.",
))
_r(TopicEntry(
    topic="growth.loop.started",
    owner="GrowthBridge",
    direction="publish",
    domain="growth",
    description="GrowthBridge hat einen DevLoop für einen Need gestartet.",
))

del _r
