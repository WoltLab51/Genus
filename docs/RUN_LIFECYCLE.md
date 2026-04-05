# RUN LIFECYCLE

This document describes the GENUS run lifecycle: what a *run* is, how run IDs
are managed, the standard lifecycle topics, and the recommended usage pattern.

---

## What is a Run?

A **run** is a single end-to-end execution of a GENUS goal or problem.  It
groups all related messages, steps, and outcomes under a shared identifier so
that observability tools, agents, and downstream consumers can correlate
activity across the system.

---

## Why is `run_id` in `Message.metadata`?

`run_id` is cross-cutting infrastructure – it belongs to every message in a
run regardless of what the message is *about*.  Keeping it in `metadata`
(rather than `payload`) preserves a clean separation:

| Field      | Purpose                                      |
|------------|----------------------------------------------|
| `payload`  | Business content specific to the topic       |
| `metadata` | Envelope / routing / correlation attributes  |

This means downstream consumers can filter or correlate by `run_id` without
knowing anything about the payload schema.

`run_id` is set and read via the helpers in `genus/core/run.py`:

```python
from genus.core.run import new_run_id, attach_run_id, get_run_id, require_run_id
```

---

## Lifecycle Topics

All constants live in `genus/run/topics.py`.

| Constant              | Topic string            | Description                                  |
|-----------------------|-------------------------|----------------------------------------------|
| `RUN_STARTED`         | `run.started`           | A new run has begun.                         |
| `RUN_STEP_PLANNED`    | `run.step.planned`      | A step has been added to the execution plan. |
| `RUN_STEP_STARTED`    | `run.step.started`      | Execution of a step has begun.               |
| `RUN_STEP_COMPLETED`  | `run.step.completed`    | A step finished successfully.                |
| `RUN_STEP_FAILED`     | `run.step.failed`       | A step finished with an error.               |
| `RUN_COMPLETED`       | `run.completed`         | The entire run finished successfully.        |
| `RUN_FAILED`          | `run.failed`            | The entire run finished with an error.       |

### Minimal payload expectations

| Topic                   | Required payload keys |
|-------------------------|-----------------------|
| `run.started`           | *(none)*              |
| `run.step.planned`      | `step_id: str`        |
| `run.step.started`      | `step_id: str`        |
| `run.step.completed`    | `step_id: str`        |
| `run.step.failed`       | `step_id: str`        |
| `run.completed`         | *(none)*              |
| `run.failed`            | *(none)*              |

Additional payload keys (e.g. `result`, `error`, `reason`) are allowed but
optional and schema-free at this layer.

---

## Message Factories

All factories live in `genus/run/events.py`.  They are **pure functions** –
no IO, no MessageBus dependency.

```python
from genus.run.events import (
    run_started_message,
    run_step_planned_message,
    run_step_started_message,
    run_step_completed_message,
    run_step_failed_message,
    run_completed_message,
    run_failed_message,
)
```

Every factory:

- Requires `run_id: str` and `sender_id: str`.
- Accepts optional `payload: dict` and optional extra `metadata: dict`.
- **Never mutates** the caller's `payload` or `metadata` dicts.
- Always stores `run_id` in `message.metadata["run_id"]` via `attach_run_id()`.

Step factories additionally require `step_id: str` and inject it into the
payload automatically.

---

## Recommended Usage Pattern

### Orchestrator

```python
from genus.core.run import new_run_id
from genus.run.events import run_started_message, run_completed_message, run_failed_message

run_id = new_run_id(slug="solve-problem")

await bus.publish(run_started_message(run_id, sender_id="orchestrator"))

try:
    # … execute steps …
    await bus.publish(run_completed_message(run_id, sender_id="orchestrator"))
except Exception as exc:
    await bus.publish(run_failed_message(
        run_id,
        sender_id="orchestrator",
        payload={"error": str(exc)},
    ))
```

### Agent / Step Executor

```python
from genus.run.events import (
    run_step_started_message,
    run_step_completed_message,
    run_step_failed_message,
)

await bus.publish(run_step_started_message(run_id, sender_id="worker-agent", step_id=step_id))

try:
    result = await do_work(step)
    await bus.publish(run_step_completed_message(
        run_id,
        sender_id="worker-agent",
        step_id=step_id,
        payload={"result": result},
    ))
except Exception as exc:
    await bus.publish(run_step_failed_message(
        run_id,
        sender_id="worker-agent",
        step_id=step_id,
        payload={"error": str(exc)},
    ))
```
