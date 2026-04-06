# DEV_LOOP – GENUS Autonomous Development Orchestration

This document describes how GENUS orchestrates autonomous software development
iterations via the **dev-loop** contracts defined in `genus/dev/`.

---

## Overview

The dev-loop enables GENUS to drive the full software development cycle –
**Plan → Implement → Test → Review → Fix** – across at least two AI instances
communicating via the shared `MessageBus`.  Human intervention is only
requested when the **Ask/Stop policy** detects a condition that requires
operator confirmation.

### Phase Correlation

Each dev-loop phase request includes a unique **`phase_id`** in the payload
to enable deterministic correlation between request and response messages.
Responder agents (Builder, Reviewer) **must mirror** the `phase_id` from
the `*.requested` message in their `*.completed` or `*.failed` response.

The orchestrator uses :func:`~genus.dev.runtime.listen_for_dev_response` to
subscribe before publishing, then waits for matching responses filtered by
both `run_id` (in metadata) and `phase_id` (in payload).

**Example - Listen-before-publish pattern:**

```python
from genus.dev.runtime import listen_for_dev_response

# Create listener - subscribes immediately
listener = listen_for_dev_response(
    bus, run_id=run_id, phase_id=phase_id,
    completed_topic=topics.DEV_PLAN_COMPLETED,
    failed_topic=topics.DEV_PLAN_FAILED,
)
try:
    # Now safe to publish - listener is already subscribed
    await bus.publish(plan_request_message)
    # Wait for response
    response = await listener.wait(timeout_s=30.0)
finally:
    listener.close()
```

The convenience function :func:`~genus.dev.runtime.await_dev_response` is
also available and handles subscription/cleanup automatically.

### Timeout Behavior

The orchestrator waits for each phase response with a configurable timeout
(default: 30 seconds).  If no matching response arrives within the timeout,
a :class:`~genus.dev.runtime.DevResponseTimeoutError` is raised and the
loop terminates with `dev.loop.failed`.

---

## Roles

| Role | Description |
|------|-------------|
| **Orchestrator** | Coordinates the loop.  Publishes `*.requested` events for each phase and subscribes to `*.completed` / `*.failed` responses.  Evaluates the Ask/Stop policy after each review. |
| **Builder** | Implements changes.  Subscribes to `dev.plan.completed` and `dev.implement.requested`; publishes `dev.implement.completed` (or `dev.implement.failed`). |
| **Reviewer** | Inspects code and tests.  Subscribes to `dev.implement.completed` and `dev.test.completed`; publishes `dev.review.completed` with structured findings. |

All three roles communicate exclusively through `MessageBus` – they never call
each other directly.

---

## Topic List

All topic strings are defined as constants in `genus/dev/topics.py` and
collected in `ALL_DEV_TOPICS`.

### Loop Lifecycle

| Constant | Topic String |
|----------|-------------|
| `DEV_LOOP_STARTED` | `dev.loop.started` |
| `DEV_LOOP_COMPLETED` | `dev.loop.completed` |
| `DEV_LOOP_FAILED` | `dev.loop.failed` |

### Planning Phase

| Constant | Topic String |
|----------|-------------|
| `DEV_PLAN_REQUESTED` | `dev.plan.requested` |
| `DEV_PLAN_COMPLETED` | `dev.plan.completed` |
| `DEV_PLAN_FAILED` | `dev.plan.failed` |

### Implementation Phase

| Constant | Topic String |
|----------|-------------|
| `DEV_IMPLEMENT_REQUESTED` | `dev.implement.requested` |
| `DEV_IMPLEMENT_COMPLETED` | `dev.implement.completed` |
| `DEV_IMPLEMENT_FAILED` | `dev.implement.failed` |

### Testing Phase

| Constant | Topic String |
|----------|-------------|
| `DEV_TEST_REQUESTED` | `dev.test.requested` |
| `DEV_TEST_COMPLETED` | `dev.test.completed` |
| `DEV_TEST_FAILED` | `dev.test.failed` |

### Review Phase

| Constant | Topic String |
|----------|-------------|
| `DEV_REVIEW_REQUESTED` | `dev.review.requested` |
| `DEV_REVIEW_COMPLETED` | `dev.review.completed` |
| `DEV_REVIEW_FAILED` | `dev.review.failed` |

### Fix Phase

| Constant | Topic String |
|----------|-------------|
| `DEV_FIX_REQUESTED` | `dev.fix.requested` |
| `DEV_FIX_COMPLETED` | `dev.fix.completed` |
| `DEV_FIX_FAILED` | `dev.fix.failed` |

---

## Message Flow Diagram

```
Orchestrator                Builder              Reviewer
     │                          │                    │
     │── dev.loop.started ──────►│                    │
     │                          │                    │
     │── dev.plan.requested ────►│                    │
     │◄─ dev.plan.completed ─────│                    │
     │                          │                    │
     │── dev.implement.requested►│                    │
     │◄─ dev.implement.completed─│                    │
     │                          │                    │
     │── dev.test.requested ────►│                    │
     │◄─ dev.test.completed ─────│                    │
     │                          │                    │
     │── dev.review.requested ───────────────────────►│
     │◄─ dev.review.completed ───────────────────────│
     │                          │                    │
     │  [Ask/Stop policy gate]  │                    │
     │       │                  │                    │
     │  ask? │─── notify user ──────────────────────►│ (paused)
     │  no   │                  │                    │
     │       │                  │                    │
     │  [fixes needed?]         │                    │
     │       │── dev.fix.requested ─────────────────►│
     │       │◄─ dev.fix.completed ─────────────────│
     │       │                  │                    │
     │── dev.loop.completed ────►│                    │
```

If any phase publishes a `*.failed` event, the Orchestrator publishes
`dev.loop.failed` and the loop terminates.

---

### Factory notes

- **`context`** in `dev_loop_started_message` is always normalised to a plain
  `dict` – it is never `None` in the produced message payload.  Pass
  `context={"repo": "WoltLab51/Genus", "branch": "main"}` or omit the
  argument to get an empty dict `{}`.



Artifact shapes are documented as dataclasses in `genus/dev/schemas.py`.
Events carry plain `dict` payloads (JSON-compatible); these dataclasses
exist for documentation and type-checked construction.

| Schema | Purpose |
|--------|---------|
| `PlanArtifact` | Output of the planning phase: steps, acceptance criteria, risks. |
| `TestReportArtifact` | Test run results: passed/failed counts, duration, failing test IDs. |
| `ReviewArtifact` | Code review output: findings with severities, required fixes. |
| `FixArtifact` | Applied fixes: patch summary, changed files, tests re-run. |

Use `dataclasses.asdict(artifact)` to convert to a JSON-compatible dict before
embedding in a message payload.

---

## Ask/Stop Policy

The policy is implemented as a pure, deterministic function in
`genus/dev/policy.py`:

```python
should_ask_user(
    findings: list[dict],
    risks: list[dict],
    scope_change: bool,
    security_impact: bool,
) -> tuple[bool, str]
```

### Rules (in priority order)

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | `security_impact=True` | Ask – security confirmation required |
| 2 | `scope_change=True` | Ask – scope change confirmation required |
| 3 | Any finding has `severity >= "high"` (high or critical) | Ask – operator review required |
| 4 | None of the above | Do not ask – loop continues automatically |

Severity order (lowest → highest): `none < info < low < medium < high < critical`.

### Return value

- `(True, "<reason>")` – the loop must pause and ask the operator.
- `(False, "")` – the loop may continue without interruption.

### Example

```python
from genus.dev.policy import should_ask_user

ask, reason = should_ask_user(
    findings=[{"severity": "high", "message": "SQL injection risk"}],
    risks=[],
    scope_change=False,
    security_impact=False,
)
# ask == True, reason == "Finding with severity 'high' requires operator review."
```

---

## Reference Agent Skeletons (genus/dev/agents/)

GENUS includes reference agent implementations that demonstrate the MessageBus
communication pattern. These agents are **placeholder skeletons** – they do not
perform actual operations (no filesystem, subprocess, or network access). They
serve as blueprints for real agents.

| Agent | Subscribes To | Publishes |
|-------|---------------|-----------|
| **PlannerAgent** | `dev.plan.requested` | `dev.plan.completed` or `dev.plan.failed` |
| **BuilderAgent** | `dev.implement.requested` | `dev.implement.completed` or `dev.implement.failed` |
| **TesterAgent** | `dev.test.requested` | `dev.test.completed` or `dev.test.failed` |
| **ReviewerAgent** | `dev.review.requested` | `dev.review.completed` or `dev.review.failed` |

All agents extend :class:`~genus.dev.agents.base.DevAgentBase`, which provides
idempotent `start()` / `stop()` lifecycle management and subscription cleanup.

### Configuration

Each agent supports optional configuration for testing:

- **mode**: `"ok"` (normal) or `"fail"` (simulate failure)
- **fail_topic**: Optional topic filter for failure mode

**ReviewerAgent** additionally supports:

- **review_profile**: `"clean"` (no findings) or `"high_sev"` (high severity finding)

### Example Usage

```python
from genus.communication.message_bus import MessageBus
from genus.dev.agents import PlannerAgent, BuilderAgent, TesterAgent, ReviewerAgent
from genus.dev.devloop_orchestrator import DevLoopOrchestrator

bus = MessageBus()

# Create and start agents
planner = PlannerAgent(bus, mode="ok")
builder = BuilderAgent(bus, mode="ok")
tester = TesterAgent(bus, mode="ok")
reviewer = ReviewerAgent(bus, review_profile="clean")

planner.start()
builder.start()
tester.start()
reviewer.start()

# Create and run orchestrator
orchestrator = DevLoopOrchestrator(bus, timeout_s=30.0)
await orchestrator.run(run_id="test-run-001", goal="Implement feature X")

# Clean up
planner.stop()
builder.stop()
tester.stop()
reviewer.stop()
```

---

## File Layout

```
genus/dev/
├── __init__.py                # Package marker
├── topics.py                  # Topic string constants + ALL_DEV_TOPICS
├── events.py                  # Message factory functions (with phase_id support)
├── schemas.py                 # Artifact dataclasses (PlanArtifact, etc.)
├── policy.py                  # Ask/Stop policy (should_ask_user)
├── runtime.py                 # Runtime helpers (await_dev_response, exceptions)
├── devloop_orchestrator.py    # Real orchestrator with await logic
└── agents/                    # Reference agent skeletons
    ├── __init__.py
    ├── base.py                # DevAgentBase (lifecycle management)
    ├── planner_agent.py       # PlannerAgent
    ├── builder_agent.py       # BuilderAgent
    ├── tester_agent.py        # TesterAgent
    └── reviewer_agent.py      # ReviewerAgent

tests/unit/
├── test_dev_topics.py         # Topic constants tests
├── test_dev_events.py         # Factory function tests
├── test_dev_policy.py         # Policy rule tests
├── test_dev_runtime.py        # Runtime helper tests
└── test_devloop_orchestrator_runtime.py  # Orchestrator runtime tests

tests/integration/
└── test_devloop_with_agents.py  # End-to-end integration tests with agents
```

---

## Constraints

- **No subprocess execution** – the orchestrator awaits responses but does not execute tools directly.
- **No FastAPI changes** – dev-loop contracts are transport-agnostic.
- **No Redis required** – unit tests use the in-memory `MessageBus`.
- **No changes to existing Orchestrator/ToolExecutor** – fully additive.
