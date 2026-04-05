# Redis Transport for GENUS

This document describes how to run the Orchestrator and ToolExecutor as
**separate processes** communicating over Redis Pub/Sub.

---

## Architecture

```
┌──────────────────────┐         Redis Pub/Sub        ┌──────────────────────┐
│   Orchestrator CLI   │ ──── tool.call.requested ───► │  ToolExecutor CLI    │
│  (process A)         │ ◄─── tool.call.succeeded ──── │  (process B)         │
│                      │ ◄─── tool.call.failed  ─────── │                      │
└──────────────────────┘                               └──────────────────────┘
```

Both processes connect to Redis independently.  All GENUS topic strings map
1-to-1 to Redis channel names.  Messages are serialised as JSON.

> **Limitation — exact topics only:** `RedisMessageBus.subscribe()` supports
> **exact topic strings only**.  Wildcard patterns (e.g. `tool.call.*`) are
> **not supported** and will raise a `ValueError` immediately.  Subscribe to
> each concrete topic explicitly instead.

---

## Quickstart

### 1. Start Redis

```bash
docker compose -f docker-compose.redis.yml up -d
```

Verify Redis is up:

```bash
redis-cli ping   # should print PONG
```

### 2. Install the `redis` package

```bash
pip install "redis[asyncio]>=4.0"
```

### 3. Start the ToolExecutor (Terminal A)

```bash
export GENUS_REDIS_URL=redis://localhost:6379/0   # optional, this is the default

python -m genus.cli.tool_executor
```

Expected output:

```
2026-04-05T19:40:00 [ToolExecutor] INFO Connecting to Redis at redis://localhost:6379/0
2026-04-05T19:40:00 [ToolExecutor] INFO ToolExecutor ready.  Listening on 'tool.call.requested'.  Supported tools: add, echo, summarize
```

### 4. Run the Orchestrator (Terminal B)

```bash
export GENUS_REDIS_URL=redis://localhost:6379/0

# Default demo run (echo + summarize)
python -m genus.cli.orchestrator

# Custom problem
python -m genus.cli.orchestrator --problem "add 3 and 4"
```

Expected output:

```
2026-04-05T19:40:05 [Orchestrator] INFO Connecting to Redis at redis://localhost:6379/0
2026-04-05T19:40:05 [Orchestrator] INFO Starting run for problem: 'demo problem: echo and summarize'
2026-04-05T19:40:05 [Orchestrator] INFO Run completed successfully: run_id=2026-04-05T19-40-05Z__demo-problem-echo-and-summa__k3m9f2
```

### 5. Stop Redis

```bash
docker compose -f docker-compose.redis.yml down
```

---

## Environment Variables

| Variable            | Default                      | Description                        |
|---------------------|------------------------------|------------------------------------|
| `GENUS_REDIS_URL`   | `redis://localhost:6379/0`   | Redis connection URL               |

---

## Supported Tools (ToolExecutor Whitelist)

The ToolExecutor uses a **ToolRegistry** to manage available tools. Tools are
registered at startup and looked up from the registry when handling requests.
Unknown tools return a `tool.call.failed` response.

| Tool name   | Arguments              | Result                          |
|-------------|------------------------|---------------------------------|
| `echo`      | `message: str`         | Returns `message` unchanged     |
| `add`       | `a: int, b: int`       | Returns `a + b`                 |
| `summarize` | `text: str`            | Returns `"summary: " + text`    |

Any unknown tool name results in a `tool.call.failed` response.

### Registering Custom Tools

To add your own tools to the ToolExecutor:

1. Create a tool function (sync or async):
   ```python
   def my_tool(arg1: str, arg2: int) -> str:
       return f"{arg1}: {arg2}"
   ```

2. Register it in the ToolExecutor's `_build_registry()` function:
   ```python
   from genus.tools.registry import ToolSpec
   from my_module import my_tool

   def _build_registry() -> ToolRegistry:
       registry = ToolRegistry()
       registry.register(ToolSpec(name="echo", handler=echo))
       registry.register(ToolSpec(name="add", handler=add))
       registry.register(ToolSpec(name="summarize", handler=summarize))
       registry.register(ToolSpec(name="my_tool", handler=my_tool, description="My custom tool"))
       return registry
   ```

The ToolRegistry enforces a deny-by-default policy: only explicitly registered
tools can be executed.

---

## Tool Registry

The ToolExecutor uses `genus.tools.registry.ToolRegistry` to manage tools:

- **Deny by default**: Unknown tools are rejected immediately
- **No accidental overwrites**: Registering the same tool twice raises `ValueError`
  unless `replace=True` is explicitly passed
- **Sync and async support**: Tool handlers can be either synchronous or
  asynchronous functions
- **No dependencies**: The registry has no Redis or IO dependencies

See `genus/tools/registry.py` for implementation details and
`tests/unit/test_tool_registry.py` for examples.

---

## Module Overview

| Module                                           | Purpose                                           |
|--------------------------------------------------|---------------------------------------------------|
| `genus/communication/serialization.py`           | `message_to_dict` / `message_from_dict` helpers  |
| `genus/communication/transports/redis_pubsub.py` | Low-level Redis Pub/Sub adapter                   |
| `genus/communication/redis_message_bus.py`       | `RedisMessageBus` (same API as `MessageBus`)      |
| `genus/communication/secure_bus.py`              | `SecureMessageBus` – wraps any bus with kill-switch + ACL |
| `genus/tools/registry.py`                        | `ToolRegistry` – central tool registration/lookup |
| `genus/tools/impl/`                              | Standard tool implementations (echo, add, summarize) |
| `genus/security/acl_presets.py`                  | Predefined ACL policies for common scenarios      |
| `genus/cli/tool_executor.py`                     | Standalone ToolExecutor process                   |
| `genus/cli/orchestrator.py`                      | Standalone Orchestrator process                   |
| `docker-compose.redis.yml`                       | Docker Compose for local Redis                    |

---

## Running Tests

Unit tests run without Redis and are always enabled:

```bash
python -m pytest tests/unit/ -v
```

Optional integration tests run only when `GENUS_REDIS_URL` is set:

```bash
export GENUS_REDIS_URL=redis://localhost:6379/0
python -m pytest tests/integration/test_redis_transport.py -v
```

Without `GENUS_REDIS_URL`, the integration tests are automatically skipped.
