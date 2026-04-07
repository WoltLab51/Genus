# GENUS – Architektur-Übersicht

> **Stand:** 2026-04-07 | Sprache: Deutsch

---

## 1. Grundprinzip: Clean Architecture

GENUS folgt dem Clean-Architecture-Prinzip mit einer **strikten Dependency-Richtung**:

```
┌───────────────────────────────────────────────┐
│          Agents / API / Tools (äußerste Schicht) │
│   ┌───────────────────────────────────────┐   │
│   │      Communication (MessageBus)       │   │
│   │   ┌───────────────────────────────┐   │   │
│   │   │  Core (Abstractions, run_id)  │   │   │
│   │   └───────────────────────────────┘   │   │
│   └───────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
```

**Regel:** Jede Schicht darf nur **innen** liegende Schichten kennen, nie äußere.

| Modul | Abhängigkeiten |
|---|---|
| `genus/core/` | Keine (nullabhängig) |
| `genus/communication/` | `genus/core/` |
| `genus/quality/` | `genus/core/` |
| `genus/memory/` | `genus/core/`, `genus/communication/` |
| `genus/agents/` | `genus/core/`, `genus/communication/`, `genus/quality/`, `genus/memory/` |
| `genus/security/` | `genus/core/` | TopicAclPolicy, KillSwitch, Rollenmodell, SanitizationPolicy |
| `genus/api/` | Alle Module (Kompositions-Root) – **✅ Phase 1 implementiert** |

---

## 2. Modulgrenzen

### `genus/core/` – Kern-Abstraktionen
| Datei | Verantwortung |
|---|---|
| `agent.py` | Abstrakte Basisklasse `Agent`, `AgentState` (INITIALIZED/RUNNING/PAUSED/STOPPED/ERROR) |
| `lifecycle.py` | `Lifecycle`-Manager: startet/stoppt mehrere Agenten koordiniert |
| `run.py` | `new_run_id()`, `RunContext`, `attach_run_id()`, `get_run_id()`, `require_run_id()` |
| `memory.py` | Einfacher persistenter Speicher (memory.json, Good-Ratio-Statistik) |
| `logger.py` | Einheitliches Logging |
| `config.py` | `Config`-Klasse, liest `API_KEY` und andere ENV-Variablen |

### `genus/communication/` – Nachrichtenaustausch
| Datei | Verantwortung |
|---|---|
| `message_bus.py` | `MessageBus` (Publish-Subscribe), `Message`, `MessagePriority` |

**Wichtig:** Der MessageBus unterstützt **keine Wildcard-Subscriptions**. Topics müssen exakt übereinstimmen (z. B. `"analysis.completed"`, nicht `"analysis.*"`).

### `genus/quality/` – Qualitätsbewertung
| Datei | Verantwortung |
|---|---|
| `scorecard.py` | `QualityScorecard` Dataclass: `overall`, `dimensions`, `evidence` |

### `genus/memory/` – Event-Persistenz (Memory 2.0)
| Datei | Verantwortung |
|---|---|
| `event_store.py` | Abstraktes `EventStore`-Interface (`append`, `iter`, `latest`) |
| `jsonl_event_store.py` | `JsonlEventStore`: append-only JSONL, eine Datei pro run_id; `EventEnvelope` Dataclass |

### `genus/agents/` – Konkrete Agenten
| Agent | Subscriptions | Publikationen | Status |
|---|---|---|---|
| `DataCollectorAgent` | – (externer Input) | `data.collected` | ✅ |
| `AnalysisAgent` | `data.collected` | `analysis.completed` | ✅ |
| `QualityAgent` | `analysis.completed`, `data.analyzed` | `quality.scored` | ✅ |
| `DecisionAgent` | `quality.scored` | `decision.made` | ✅ |
| `EventRecorderAgent` | Whitelist-Topics | – (schreibt in EventStore) | ✅ |
| `FeedbackAgent` | `outcome.recorded` | `feedback.received` | ✅ |
| `DataSanitizerAgent` | `data.collected` | `data.sanitized` | ✅ |

### `genus/security/` – Sicherheitsschicht
| Datei | Verantwortung |
|---|---|
| `topic_acl.py` | `TopicAclPolicy`: exact-match Sender→Topic Whitelist |
| `kill_switch.py` | `KillSwitch`: globaler Notfall-Stop für `MessageBus.publish()` |
| `roles.py` | `Role` Enum (READER/OPERATOR/ADMIN), `topics_for_role()` |
| `role_acl.py` | `build_policy_from_roles()`: Rollen → TopicAclPolicy |
| `acl_presets.py` | `default_pipeline_policy()`, `default_orchestrator_toolexecutor_policy()` |
| `sanitization/` | `SanitizationPolicy`, `sanitize_payload()` |

### `genus/api/` – REST-API (FastAPI) — Phase 1 ✅
| Datei | Verantwortung |
|---|---|
| `app.py` | `create_app()`: FastAPI App-Factory, Lifespan-Kontext, Middleware-Wiring |
| `middleware.py` | `ApiKeyMiddleware`: Bearer-Token-Prüfung (`Authorization: Bearer <key>`), exempt: `/health` |
| `errors.py` | `ErrorHandlingMiddleware`: strukturierte JSON-Fehlerantworten, kein Stack-Trace |
| `deps.py` | FastAPI Dependencies: `get_message_bus()`, `verify_operator()` |
| `routers/health.py` | `GET /health` — Liveness-Check, kein Auth |
| `routers/runs.py` | `POST /runs` — Run starten via `run.started` auf MessageBus |
| `routers/outcome.py` | `POST /outcome` — Feedback via `outcome.recorded` auf MessageBus |

---

## 3. Agent-Lifecycle

Jeder Agent durchläuft diesen festen Lifecycle:

```
__init__()          → Abhängigkeiten injizieren (KEIN subscribe hier!)
    ↓
initialize()        → Auf Topics subscriben, Zustand: INITIALIZED
    ↓
start()             → Zustand: RUNNING
    ↓
[process_message()] → Nachrichten verarbeiten (async)
    ↓
stop()              → Unsubscribe, Zustand: STOPPED
```

**Invariante:** Subscriptions dürfen **ausschließlich** in `initialize()` stattfinden, nie in `__init__`.

### Beispiel: Minimaler Agent

```python
from genus.core.agent import Agent, AgentState
from genus.communication.message_bus import Message, MessageBus

class MyAgent(Agent):
    def __init__(self, message_bus: MessageBus, name: str = "MyAgent"):
        super().__init__(name=name)
        self._bus = message_bus

    async def initialize(self) -> None:
        self._bus.subscribe("some.topic", self.id, self.process_message)
        self._transition_state(AgentState.INITIALIZED)

    async def start(self) -> None:
        self._transition_state(AgentState.RUNNING)

    async def stop(self) -> None:
        self._bus.unsubscribe_all(self.id)
        self._transition_state(AgentState.STOPPED)

    async def process_message(self, message: Message) -> None:
        # Verarbeitung...
        pass
```

---

## 4. MessageBus-Nutzung

```python
from genus.communication.message_bus import Message, MessageBus

bus = MessageBus()

# Subscriben (immer in initialize())
bus.subscribe("analysis.completed", agent.id, agent.process_message)

# Publizieren
msg = Message(topic="analysis.completed", payload={"score": 0.9})
await bus.publish(msg)

# Alle Subscriptions eines Agenten entfernen (in stop())
bus.unsubscribe_all(agent.id)
```

**Achtung:** `bus.publish()` ist `async` und muss mit `await` aufgerufen werden.

---

## 5. run_id – Propagation

Die `run_id` identifiziert eindeutig einen GENUS-Run und wird in `Message.metadata` mitgeführt:

```python
from genus.core.run import new_run_id, attach_run_id, get_run_id, require_run_id

run_id = new_run_id()          # z. B. "2026-04-05T15-30-00__analyze__abc123"
msg = Message(topic="...", payload={})
attach_run_id(msg, run_id)     # Setzt msg.metadata["run_id"] = run_id

# In einem Agent:
run_id = get_run_id(message)   # Gibt None zurück, wenn nicht gesetzt
run_id = require_run_id(message)  # Wirft Exception, wenn nicht gesetzt
```

---

## 6. Wo passen geplante Komponenten hin?

| Komponente | Schicht | Abhängigkeiten | Bemerkung |
|---|---|---|---|
| **Orchestrator** | `genus/orchestration/` | core, communication, agents | Koordiniert Multi-Agent-Workflows |
| **Builder** | `genus/builder/` | core, agents | Erstellt Agenten aus Konfiguration |
| **Sandbox** | `genus/sandbox/` | core | Isolierte Tool-Ausführung |
| **DataSanitizerAgent** | `genus/agents/` | core, communication, memory | Nächster geplanter Agent (P1-C) |
| **Permissions/Rollen** | `genus/security/` | core, api | ✅ Rollenmodell implementiert: Role.READER/OPERATOR/ADMIN |
| **API-Layer Phase 1** | `genus/api/` | core, communication | ✅ /health, /runs, /outcome |
| **API Phase 2** | `genus/api/routers/` | security | /kill-switch (Admin only) |
