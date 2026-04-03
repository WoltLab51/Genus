# Migration Notes

> What changed from the three original branches and why.

## Source Branches

| Branch | Focus |
|---|---|
| `copilot/build-genus-modular-ai-system` | Working pipeline (DataCollector → Analysis → Decision), FastAPI, Next.js frontend, Docker |
| `claude/improve-genus-modular-architecture` | Clean Agent ABC, AgentState enum, MessageBus with wildcards, Lifecycle, Config |
| `claude/implement-feedback-system-genus` | Decision / Feedback persistence, REST API for feedback, EventBus for observability |

## Unified Architecture

### 1. Single MessageBus (replaces duplicated EventBus / MessageBus)

**Before:** Three different messaging implementations across branches.

- copilot: `EventBus` (simple exact-match, dict payloads)
- claude/improve: `MessageBus` (Message dataclass, subscriber IDs, wildcards)
- claude/feedback: `MessageBus` (Message dataclass) + `EventBus` (Event dataclass, observability)

**After:** One `MessageBus` class with a `Message` dataclass.

- Combines agent communication *and* observability in one transport.
- Capped message history replaces the separate `EventBus` log.
- Wildcard routing was dropped because no agent currently uses it — can be
  re-added without breaking changes.

### 2. Agent Lifecycle (subscriptions moved out of `__init__`)

**Before (copilot):** `AnalysisAgent.__init__()` and `DecisionAgent.__init__()` called
`self.bus.subscribe(...)` — a side-effect-in-constructor anti-pattern.

**After:** Agents have explicit `initialize()` / `start()` / `stop()` methods
(taken from claude/improve).  `initialize()` is where subscriptions happen.
`stop()` unsubscribes.  The `Lifecycle` manager coordinates startup/shutdown.

### 3. No Global Singletons

**Before (copilot):** Module-level singletons for `event_bus`, `memory_store`, and every agent.
Tests had to monkey-patch `.memory` and `.bus` attributes to isolate.

**After:** Everything is created inside the FastAPI lifespan context or test
fixture.  Constructor injection throughout.

### 4. Unified Storage

**Before:**
- copilot: `MemoryStore` (in-memory KV), `database.py` (SQLAlchemy engine shell — no ORM models, `init_db()` never called)
- claude/feedback: `MemoryStore` (confusingly named DB-backed DecisionStore), `FeedbackStore`, ORM `Decision` + `Feedback`

**After:**
- `MemoryStore` = in-memory KV (from copilot, with bounded history)
- `DecisionStore` = async DB-backed Decision store (renamed from feedback branch `MemoryStore`)
- `FeedbackStore` = async DB-backed Feedback store (from feedback branch)
- `init_db()` called properly during lifespan startup

### 5. ORM Models Used

**Before (copilot):** `Base` declared but zero subclasses. PostgreSQL container provisioned but DB never populated.

**After:** Two SQLAlchemy models (`Decision`, `Feedback`) with a one-to-many
relationship.  `init_db()` creates tables on startup.

### 6. Flat Package Structure

**Before (copilot):** `backend/agents/data_collector/agent.py` — deeply nested sub-packages.

**After:** `genus/agents/data_collector.py` — flat modules.  Each agent is one file.

### 7. Schema Refactoring

**Before:** copilot branch used Pydantic models (`DataItem`, `AnalysisResult`, `Decision`)
as both internal data structures and API payloads.

**After:** Agents work with plain dicts internally.  Pydantic schemas in `api/schemas.py`
are used only for API request/response validation, keeping the agent layer free from
web-framework dependencies.

### 8. App Factory

**Before (copilot):** A single `app = FastAPI(...)` module-level object.

**After:** `create_app(database_url=..., config=...)` factory function.
Tests pass an in-memory DB URL; production passes PostgreSQL.

### 9. What Was Removed

| Item | Reason |
|---|---|
| copilot `backend/` top-level directory | Unified into `genus/` package |
| copilot `GenusLogger` wrapper | Standard `logging.getLogger()` is sufficient |
| claude/improve `Config` singleton | Config is now a plain class passed explicitly |
| claude/feedback `EventBus` | Merged into `MessageBus` |
| claude/improve wildcard topic matching | Unused; can be re-added later |
| `frontend/` (Next.js) | Not modified — can be wired back to the new API |
| `docker-compose.yml` | Not modified — can be updated to new package paths |

### 10. What Was Preserved

| Item | Source |
|---|---|
| SSRF mitigation in DataCollectorAgent | copilot |
| Agent state machine (AgentState enum) | claude/improve |
| ORM models (Decision, Feedback) | claude/feedback |
| FeedbackStore validation (score range, label enum) | claude/feedback |
| Lifecycle manager | claude/improve |
| API routes for decisions and feedback | claude/feedback |
| Pipeline route (`/system/pipeline/run`) | copilot |
| MemoryStore (in-memory KV) | copilot |
