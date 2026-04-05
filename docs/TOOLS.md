# GENUS – Tool-Call Delegation (Tool-Oriented Topics)

> **Stand:** 2026-04-05 | Option 2 – `tool.call.*` Topics

---

## Übersicht

Die GENUS-Orchestrierung delegiert Werkzeugaufrufe (**Tool Calls**) über den
MessageBus.  Für jeden Schritt in einem Run publiziert der Orchestrator eine
`tool.call.requested`-Nachricht; ein Tool-Executor-Agent verarbeitet sie und
antwortet mit `tool.call.succeeded` oder `tool.call.failed`.

```
Orchestrator                     MessageBus              ToolExecutorAgent
     │  tool.call.requested ───────► │ ─────────────────────► │
     │                               │                         │
     │ ◄─── tool.call.succeeded ──── │ ◄───────────────────── │
     │       (oder .failed)          │
```

---

## Korrelationsschlüssel

| Feld | Wo | Beschreibung |
|------|----|--------------|
| `run_id` | `Message.metadata["run_id"]` | Identifiziert den laufenden Run (gesetzt via `attach_run_id()`) |
| `step_id` | `Message.payload["step_id"]` | UUID-String; identifiziert einen Einzelschritt eindeutig innerhalb eines Runs |

Jede `tool.call.*`-Nachricht enthält **beide** Korrelationsfelder.  Der
Orchestrator korreliert eingehende Antworten via `(run_id, step_id)`.

---

## Topics

| Topic | Publisher | Subscriber | Bedeutung |
|-------|-----------|------------|-----------|
| `tool.call.requested` | Orchestrator | ToolExecutorAgent(s) | Werkzeugaufruf anfordern |
| `tool.call.succeeded` | ToolExecutorAgent | Orchestrator | Ergebnis des Werkzeugs |
| `tool.call.failed` | ToolExecutorAgent | Orchestrator | Fehler beim Werkzeugaufruf |

Konstanten: `genus.tools.topics`

---

## Payload-Schema

### `tool.call.requested`

```json
{
  "step_id":   "<uuid4>",
  "tool_name": "echo",
  "tool_args": { "message": "hello" }
}
```

### `tool.call.succeeded`

```json
{
  "step_id":   "<uuid4>",
  "tool_name": "echo",
  "result":    "hello"
}
```

### `tool.call.failed`

```json
{
  "step_id":   "<uuid4>",
  "tool_name": "echo",
  "error":     "Human-readable error description"
}
```

---

## Message-Factories (`genus/tools/events.py`)

```python
from genus.tools.events import (
    tool_call_requested_message,
    tool_call_succeeded_message,
    tool_call_failed_message,
)

# Orchestrator – Schritt anfordern
msg = tool_call_requested_message(
    run_id, sender_id, step_id, "echo", {"message": "hello"}
)

# Tool-Executor – Ergebnis zurückgeben
msg = tool_call_succeeded_message(
    run_id, sender_id, step_id, "echo", result="hello"
)

# Tool-Executor – Fehler melden
msg = tool_call_failed_message(
    run_id, sender_id, step_id, "echo", error="tool not found"
)
```

Alle Factories:
- kopieren `payload` und `metadata` defensiv (keine Mutation der Eingabe),
- setzen `step_id` und `tool_name` im Payload,
- hängen `run_id` via `attach_run_id()` in `metadata` an.

---

## Run-Lifecycle-Sequenz

```
run.started
run.step.planned  (× N – einmal pro Step)
  run.step.started
  tool.call.requested   ──► Tool-Executor
  tool.call.succeeded   ◄── Tool-Executor
  run.step.completed
  …
run.completed
```

Bei einem fehlerhaften Step:

```
  tool.call.failed      ◄── Tool-Executor
  run.step.failed
run.failed
```

---

## Orchestrator-Nutzung

```python
from genus.communication.message_bus import MessageBus
from genus.orchestration.orchestrator import Orchestrator

bus = MessageBus()
orc = Orchestrator(bus)
await orc.initialize()

run_id = await orc.run("Erstelle eine Zusammenfassung des Berichts")
```

Für eigene Schritte:

```python
run_id = await orc.run(
    "custom-run",
    steps=[
        {"tool_name": "fetch", "tool_args": {"url": "https://example.com"}},
        {"tool_name": "summarize", "tool_args": {"text": "..."}},
    ],
)
```

---

## Invarianten

1. `step_id` ist immer eine UUID4-Zeichenkette (nie `"step-1"` o. Ä.).
2. `run_id` ist immer im Format `timestamp__slug__suffix` (Format aus `genus.core.run`).
3. Keine Mutation von übergebenen `payload`- oder `metadata`-Dicts.
4. Der Orchestrator wartet sequenziell auf jeden Schritt (`asyncio.Future`).
