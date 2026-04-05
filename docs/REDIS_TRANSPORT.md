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

> **Limitation:** Topic wildcards (e.g. `tool.call.*`) are evaluated
> in-process after receiving a message from the exact Redis channel.
> At the Redis level only exact-match channel subscriptions are used.

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

| Tool name   | Arguments              | Result                          |
|-------------|------------------------|---------------------------------|
| `echo`      | `message: str`         | Returns `message` unchanged     |
| `add`       | `a: int, b: int`       | Returns `a + b`                 |
| `summarize` | `text: str`            | Returns `"summary: " + text`    |

Any unknown tool name results in a `tool.call.failed` response.

---

## Module Overview

| Module                                           | Purpose                                           |
|--------------------------------------------------|---------------------------------------------------|
| `genus/communication/serialization.py`           | `message_to_dict` / `message_from_dict` helpers  |
| `genus/communication/transports/redis_pubsub.py` | Low-level Redis Pub/Sub adapter                   |
| `genus/communication/redis_message_bus.py`       | `RedisMessageBus` (same API as `MessageBus`)      |
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
