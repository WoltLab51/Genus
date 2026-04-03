# GENUS Architecture

> Unified modular architecture — consolidating copilot/build, claude/improve,
> and claude/feedback into one consistent design.

## Directory Structure

```
genus/
├── core/               # Abstractions and lifecycle
│   ├── agent.py        # Agent ABC, AgentState enum
│   ├── lifecycle.py    # Lifecycle manager (register/start/stop)
│   └── config.py       # Layered configuration (defaults + env vars)
├── communication/      # Single message transport
│   └── message_bus.py  # Unified pub-sub MessageBus + Message dataclass
├── storage/            # Persistence + ephemeral state
│   ├── models.py       # SQLAlchemy ORM: Decision, Feedback
│   ├── store.py        # DecisionStore, FeedbackStore (async, DB-backed)
│   └── memory.py       # MemoryStore (in-memory KV with namespaces)
├── agents/             # Concrete agent implementations
│   ├── data_collector.py
│   ├── analysis.py
│   └── decision.py
└── api/                # REST interface
    ├── app.py          # FastAPI app factory (create_app)
    └── schemas.py      # Pydantic request/response models
```

## Core Principles

### 1. No Global Singletons

Every component — bus, stores, agents — is created inside the FastAPI
lifespan context and passed to dependents by constructor injection.
Tests create their own instances so each test is fully isolated.

### 2. One Message Bus

The previous codebase had two overlapping concepts:

| Before (copilot/build) | Before (claude/feedback) | Now |
|---|---|---|
| `EventBus` in `messaging.py` | `MessageBus` + `EventBus` | **`MessageBus`** only |

A single `MessageBus` handles both agent-to-agent communication **and**
observability logging (message history).  Every published message is
automatically recorded in a capped history that the `/system/events`
endpoint can query.

### 3. Agent Lifecycle

```
__init__()          # inject dependencies (bus, memory)
  ↓
initialize()        # subscribe to topics, set up resources
  ↓
start()             # transition to RUNNING
  ↓
execute(payload)    # run core logic (called per request / per event)
  ↓
stop()              # unsubscribe, clean up, transition to STOPPED
```

Subscriptions happen in `initialize()`, **never** in `__init__()`.
This makes wiring explicit and prevents side-effects during construction.

### 4. Clear Storage Separation

| Class | Purpose | Backend |
|---|---|---|
| `MemoryStore` | Ephemeral KV scratch-pad for pipeline data | In-memory `dict` |
| `DecisionStore` | Persistent decision records | SQLAlchemy (SQLite / PostgreSQL) |
| `FeedbackStore` | Persistent feedback on decisions | SQLAlchemy (SQLite / PostgreSQL) |

The old `MemoryStore` name was ambiguous — in the copilot branch it meant
"in-memory KV" and in the feedback branch it meant "database-backed
decision store".  The unified architecture uses distinct names to remove
this confusion.

### 5. Dependency Direction

```
api/  →  agents/  →  core/
  ↓         ↓
storage/  communication/
```

- **core/** depends on nothing.
- **communication/** depends on nothing (Message is a dataclass).
- **storage/** depends on SQLAlchemy only.
- **agents/** depend on core (Agent ABC), communication (MessageBus), and
  storage (MemoryStore).
- **api/** wires everything together; depends on all other modules.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | System info |
| GET | `/health` | Liveness probe |
| GET | `/system/status` | All agent statuses |
| GET | `/system/memory` | MemoryStore dump or namespace query |
| GET | `/system/events` | MessageBus history (observability) |
| POST | `/system/pipeline/run` | Trigger full pipeline |
| GET / POST | `/agents/data-collector/*` | Data collector status / run / data |
| GET / POST | `/agents/analysis/*` | Analysis agent status / run / results |
| GET / POST | `/agents/decision/*` | Decision agent status / run / decisions |
| POST | `/decisions` | Create a persistent decision record |
| GET | `/decisions` | List decisions (filter by agent / type) |
| GET | `/decisions/{id}` | Get decision with its feedback |
| POST | `/feedback` | Submit feedback on a decision |
| GET | `/feedback` | List feedback (filter by label) |
| GET | `/feedback/{id}` | Get single feedback |

## Running

```bash
# Install
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Start the API server
uvicorn genus.api.app:app --factory --reload
```

Note: `create_app()` is used as an app factory — `uvicorn` calls it with the
`--factory` flag.

## Future Extensions

The architecture is designed to accommodate:

- **Orchestrator** — a higher-level agent that coordinates multi-step plans.
- **Sandbox** — isolated execution environment for untrusted code.
- **Security layer** — authentication, rate limiting, prompt-injection guards.
- **Learning loop** — use `FeedbackStore` data to improve agent decisions.
- **WebSocket events** — push real-time updates instead of polling.
